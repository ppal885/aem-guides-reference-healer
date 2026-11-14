"""The audit record: every reference that was changed from the Health check panel, with who
accepted it, what settled it, and the text before and after.

The editor sends the entries when an author applies something; this module only appends them to
a file and reads them back. No model. The record says what the editor reported: the versions in
the repository stay the authority on what a file contains.
"""
import csv
import io
import json
import os
import time

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "audit-log.jsonl")

# One row per changed reference, in the order of the columns of the download.
FIELDS = ("when", "accepted_by", "map", "file", "location", "attribute", "was", "now", "action", "settled_by",
          "reason", "text_before", "text_after")
ACTIONS = ("repair", "put back", "text kept", "reference removed")


def _text(value, limit=2000):
    return value.strip()[:limit] if isinstance(value, str) else ""


def record(map_path, accepted_by, entries, path=None, now=None):
    """Appends the entries of one press of a button. Returns how many were kept.
    An entry needs a file, an attribute and the old value; anything else may be empty."""
    when = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
    kept = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not all(_text(entry.get(k)) for k in ("file", "attribute", "was")):
            continue
        row = {field: _text(entry.get(field)) for field in FIELDS}
        row.update(when=when, map=_text(map_path), accepted_by=_text(accepted_by) or "not reported",
                   action=row["action"] if row["action"] in ACTIONS else "repair")
        kept.append(row)
    if kept:
        os.makedirs(os.path.dirname(path or PATH), exist_ok=True)
        with open(path or PATH, "a", encoding="utf-8") as handle:
            for row in kept:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(kept)


def entries(map_path=None, path=None):
    """The record, oldest first; for one map when a path is given."""
    try:
        with open(path or PATH, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue    # a line cut off by a crash does not hide the rest
        if isinstance(row, dict) and (not map_path or row.get("map") == map_path):
            rows.append(row)
    return rows


def _cell(value):
    """A spreadsheet must not read a value as a formula."""
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def as_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIELDS)
    for row in rows:
        writer.writerow([_cell(row.get(field)) for field in FIELDS])
    return out.getvalue()


def summary(rows):
    """Counts for the top of a report: {"references", "files", "by_action", "by_person", "by_what_settled_it"}."""
    def count(field):
        counts = {}
        for row in rows:
            counts[row.get(field) or ""] = counts.get(row.get(field) or "", 0) + 1
        return counts
    return {"references": len(rows), "files": len({row.get("file") for row in rows}), "by_action": count("action"),
            "by_person": count("accepted_by"), "by_what_settled_it": count("settled_by")}
