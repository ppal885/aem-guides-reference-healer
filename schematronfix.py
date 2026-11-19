"""A model's fix for Schematron findings that have no Schematron Quick Fix (garage-week PoC).

A Schematron rule that has a quick fix (sqf:fix) is fixed by code in AEM, without a model. For a
rule without one, AEM sends the finding here when the author asks for it: the rule's message and
test, the element it fired on, what the DTD allows inside that element, and a line of context.
The model answers with the element as it should be, nothing else. AEM then checks the answer
before the author sees it: the XML is well formed and valid, the same Schematron no longer reports
the finding and reports nothing new, and the rest of the topic is unchanged. A failed check comes
back here once with what failed ("feedback"), then the finding has no fix. Nothing is written here.

Batches of BATCH findings go in one call; an answer is kept by the hash of what was asked, so the
same finding asked again costs no call.
"""
import hashlib
import json
import re
import xml.etree.ElementTree as ET

import refheal

BATCH = 20
MAX_ELEMENT_CHARS = 6000
CACHE = {}

SYSTEM = """You fix findings of a Schematron, the rules a documentation team checks its DITA topics with. Each finding gives the rule's message and its test (XPath), the element the rule fired on, what the DTD allows inside that element and, when known, the topic's title and the sentence before it.

For each finding, write the element as it should be so that the rule no longer fires:
- Change as little as you can. Keep every word, element and attribute the rule does not ask you to change, in the same order, with the same ids.
- Keep the meaning. When the rule is about wording (length, a word not to use, a sentence too long), rewrite only what the rule asks for and keep the facts, names and numbers.
- When the rule needs content that the finding does not give (an id, a title, an alternative text, a note type), choose a short, plain value that fits what the element says; an id is lower case with underscores, derived from the element's text.
- Use only elements and attributes the DTD allows in that place. Return the same element (the same tag), never its parent or a fragment, and never anything outside it.
- If no fix keeps the meaning, or you would have to guess a fact, return no element for that finding and say why.

Reply with one JSON object and nothing else: {"fixes": [{"id": "<the finding's id>", "element": "<the fixed element as XML, or empty>", "note": "<one short sentence: what you changed, or why there is no fix>"}]}""" + refheal.DATA_RULE


def _key(finding):
    parts = [finding.get(k) or "" for k in ("rule", "message", "test", "element", "allowed", "feedback")]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def prompt_for(findings):
    """The findings as the model reads them: one JSON object per finding."""
    rows = []
    for f in findings:
        row = {"id": f["id"], "rule": f.get("rule") or "", "message": f.get("message") or "",
               "test": f.get("test") or "", "element": (f.get("element") or "")[:MAX_ELEMENT_CHARS]}
        for optional in ("allowed", "title", "context"):
            if f.get(optional):
                row[optional] = f[optional]
        if f.get("feedback"):
            row["your_last_answer_failed"] = f["feedback"]
        rows.append(row)
    return json.dumps({"findings": rows}, ensure_ascii=False, indent=1)


def _tag(xml):
    try:
        return ET.fromstring(xml).tag
    except ET.ParseError:
        return None


def clean(answer, findings):
    """{id: {"element", "note"}} for the answers that are an element of the same tag as the one the
    rule fired on. Anything else becomes "no fix" with the reason; AEM checks the rest."""
    asked = {f["id"]: f for f in findings}
    out = {}
    for fix in (answer or {}).get("fixes") or []:
        if not isinstance(fix, dict) or fix.get("id") not in asked:
            continue
        element = (fix.get("element") or "").strip()
        note = " ".join(str(fix.get("note") or "").split())[:300]
        want = _tag(asked[fix["id"]].get("element") or "")
        if element and _tag(element) is None:
            element, note = "", "The model's answer is not well-formed XML."
        elif element and want and _tag(element) != want:
            element, note = "", "The model returned <%s> where <%s> was asked for." % (_tag(element), want)
        out[fix["id"]] = {"element": element, "note": note}
    for fid in asked:
        out.setdefault(fid, {"element": "", "note": "The model gave no answer for this finding."})
    return out


def suggest(body, call_model):
    """{"fixes": [{"id", "element", "note", "cached"}], "model_calls"}: one answer per finding of
    body["findings"]; findings answered before are taken from the cache."""
    findings = [f for f in (body or {}).get("findings") or [] if isinstance(f, dict) and f.get("id") and f.get("element")]
    if not findings:
        raise ValueError("no findings with an id and an element")
    answers, calls = {}, 0
    todo = []
    for f in findings:
        hit = CACHE.get(_key(f))
        if hit is not None:
            answers[f["id"]] = dict(hit, cached=True)
        else:
            todo.append(f)
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        calls += 1
        for fid, fix in clean(call_model(SYSTEM, prompt_for(batch)), batch).items():
            f = next(x for x in batch if x["id"] == fid)
            if fix["element"]:
                CACHE[_key(f)] = fix
            answers[fid] = dict(fix, cached=False)
    return {"fixes": [dict(answers[f["id"]], id=f["id"]) for f in findings], "model_calls": calls}


def changed_words(before, after):
    """How many words of the element's text a fix changed; a rule about wording expects few."""
    def words(xml):
        try:
            return re.findall(r"\w+", "".join(ET.fromstring(xml).itertext()).lower())
        except ET.ParseError:
            return []
    import difflib
    a, b = words(before), words(after)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op != "equal")
