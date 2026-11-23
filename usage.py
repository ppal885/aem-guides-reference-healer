"""What the model calls of one check cost (garage-week PoC): calls, failed calls, tokens and,
when the backend reports it, money. No model.

Every model call is noted here. A check takes a mark when it starts and reads the totals since
that mark when it ends; the totals go into the plan the author reads and into out/usage-log.jsonl.
Two checks that run at the same time share the counter: their totals then include each other's
calls, and the record says so ("shared_with_another_check").
"""
import json
import os
import threading
import time

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "usage-log.jsonl")

_lock = threading.Lock()
_calls = []
_open = 0
_overlapped = False


_who = threading.local()


class as_agent:
    """Marks the model calls made inside it as one agent's: finder, reviewer, planner or chooser.
    Finders run in their own threads, so the mark is per thread; it nests and is put back on the way out."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.before = getattr(_who, "name", None)
        _who.name = self.name
        return self

    def __exit__(self, *exc):
        _who.name = self.before
        return False


def note(ok, input_tokens=0, output_tokens=0, cost_usd=None, error=None, cached=0):
    """One model call. cost_usd is None when the backend does not report money."""
    with _lock:
        _calls.append({"ok": bool(ok), "in": int(input_tokens or 0), "out": int(output_tokens or 0), "cached": int(cached or 0),
                       "who": getattr(_who, "name", None) or "other",
                       "thread": threading.get_ident(),     # so one finder's own calls can be counted
                       "cost": cost_usd, "error": (" ".join(str(error).split())[:160] if error else None)})


def tokens_of(usage):
    """(input, output) from a usage record of the CLI or the API; cached input counts as input."""
    read = (lambda key: getattr(usage, key, None)) if not isinstance(usage, dict) else usage.get
    total_in = sum(int(read(key) or 0) for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return total_in, int(read("output_tokens") or 0)


def cached_of(usage):
    """The part of the input that was read from the prompt cache (billed far below fresh input)."""
    read = (lambda key: getattr(usage, key, None)) if not isinstance(usage, dict) else usage.get
    return int(read("cache_read_input_tokens") or 0)


def start():
    global _open, _overlapped
    with _lock:
        _open += 1
        if _open > 1:
            _overlapped = True
        return len(_calls)


def position():
    """Where the record of calls stands now, to count from (unlike start(), it opens no check)."""
    with _lock:
        return len(_calls)


def failed_since(mark):
    """The model calls since mark (position()) that did not answer: (failed, all, the first reason)."""
    with _lock:
        calls = _calls[mark:]
    failed = [call for call in calls if not call["ok"]]
    return len(failed), len(calls), (failed[0].get("error") if failed else None)


# The share of an eval's model calls that may fail and the eval still give a score. One answer the
# code could not read, in a run of 80 calls (24 Nov 2026, the DITA-OT docs), leaves one target unlooked
# at; it does not make the other 79 wrong.
MOST_UNANSWERED = 0.1


def refuse_unanswered(failed, total, first, what):
    """An eval whose model calls mostly did not answer has no score: the missed or steered it would
    count are calls that failed (on 24 Nov 2026 an expired login read as "steered 8 of 8" and "missed
    432", and overwrote the stored result). Then it says so, writes nothing and exits with 3. A few
    calls that failed are said as a warning, and the eval goes on; its result keeps the count."""
    if not failed:
        return
    reason = str(first or "no reason given")[:200]
    if failed < total and failed <= MOST_UNANSWERED * total:
        print("WARNING: %d of %d model calls of %s did not answer (%s); what they were for is not in the "
              "score." % (failed, total, what, reason), flush=True)
        return
    import sys
    print("NOT SCORED: %d of %d model calls of %s did not answer (%s). Nothing was written; fix the model "
          "access and run it again." % (failed, total, what, reason), flush=True)
    sys.exit(3)


# What a token costs next to a fresh input token, from the model's price list: input read from the
# prompt cache is a tenth, output is five times. A limit counted this way follows the money: on a
# customer export 71% of the input was read from the cache.
CACHED_INPUT_WEIGHT = 0.1
OUTPUT_WEIGHT = 5


def cost_since(mark, thread=None):
    """The calls since mark in fresh-input-token terms: fresh input as it is, cached input at
    CACHED_INPUT_WEIGHT, output at OUTPUT_WEIGHT. With thread, only that thread's calls."""
    with _lock:
        calls = [call for call in _calls[mark:] if thread is None or call.get("thread") == thread]
    return sum(call["in"] - call["cached"] + call["cached"] * CACHED_INPUT_WEIGHT + call["out"] * OUTPUT_WEIGHT
               for call in calls)


def tokens_since(mark, thread=None):
    """Input and output tokens of the calls since position() or start() returned mark. A check that
    runs at the same time adds its calls too, so a limit on this stops early rather than late.
    With thread, only the calls made in that thread (one finder agent and its reviewer)."""
    with _lock:
        return sum(call["in"] + call["out"] for call in _calls[mark:] if thread is None or call.get("thread") == thread)


def finish(mark):
    """Totals of the calls since start()."""
    global _open, _overlapped
    with _lock:
        calls = _calls[mark:]
        shared = _overlapped
        _open -= 1
        if _open == 0:
            _overlapped = False
    failed = [call for call in calls if not call["ok"]]
    costs = [call["cost"] for call in calls if call["cost"] is not None]
    by_agent = {}
    for call in calls:
        mine = by_agent.setdefault(call.get("who") or "other", {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                                "read_from_cache": 0})
        mine["model_calls"] += 1
        mine["input_tokens"] += call["in"]
        mine["output_tokens"] += call["out"]
        mine["read_from_cache"] += call["cached"]
    return {"model_calls": len(calls), "failed_calls": len(failed), "by_agent": by_agent,
            "input_tokens": sum(call["in"] for call in calls),
            "of_which_read_from_cache": sum(call["cached"] for call in calls), "output_tokens": sum(call["out"] for call in calls),
            "cost_usd": round(sum(costs), 4) if costs else None,
            "first_failure": failed[0]["error"] if failed else None,
            "shared_with_another_check": shared}


def sentence(totals):
    """One line for the plan."""
    if not totals["model_calls"]:
        return "AI use in this check: none; rules, version history and earlier answers settled everything."
    money = ", about $%.2f" % totals["cost_usd"] if totals["cost_usd"] is not None else ""
    shared = " Another check ran at the same time; its calls are counted in." if totals["shared_with_another_check"] else ""
    agents = sorted((totals.get("by_agent") or {}).items(), key=lambda item: -item[1]["input_tokens"])
    split = " By agent: %s." % "; ".join("%s %d call%s, %s tokens in%s" % (
        name, use["model_calls"], "" if use["model_calls"] == 1 else "s", format(use["input_tokens"], ","),
        " (%s from the cache)" % format(use["read_from_cache"], ",") if use.get("read_from_cache") else "")
        for name, use in agents) if len(agents) > 1 else ""
    cached = totals.get("of_which_read_from_cache") or 0
    weighted = totals["input_tokens"] - cached + cached * CACHED_INPUT_WEIGHT + totals["output_tokens"] * OUTPUT_WEIGHT
    from_cache = " (%s of them read from the cache)" % format(cached, ",") if cached else ""
    return "AI use in this check: %d model call%s, %s tokens in%s and %s out, %s in cost terms%s.%s%s" % (
        totals["model_calls"], "" if totals["model_calls"] == 1 else "s", format(totals["input_tokens"], ","), from_cache,
        format(totals["output_tokens"], ","), format(int(round(weighted)), ","), money, split, shared)


def warning(totals):
    """None, or what the author must know when the model did not answer."""
    if not totals["failed_calls"]:
        return None
    return ("Warning: the AI did not answer %d of %d calls (%s). What it could not look at was not repaired by guesswork: "
            "those references are left for you to review, or have no proposal. Run the check again when the AI answers." % (
                totals["failed_calls"], totals["model_calls"], totals["first_failure"] or "no reason given"))


def record(map_path, totals, seconds, path=None):
    os.makedirs(os.path.dirname(path or LOG_PATH), exist_ok=True)
    line = dict(totals, map=map_path, seconds=seconds, when=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with _lock, open(path or LOG_PATH, "a", encoding="utf-8") as out:
        out.write(json.dumps(line, ensure_ascii=False) + "\n")


def entries(path=None):
    try:
        with open(path or LOG_PATH, encoding="utf-8") as lines:
            return [json.loads(line) for line in lines if line.strip()]
    except OSError:
        return []
