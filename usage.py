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


def note(ok, input_tokens=0, output_tokens=0, cost_usd=None, error=None, cached=0):
    """One model call. cost_usd is None when the backend does not report money."""
    with _lock:
        _calls.append({"ok": bool(ok), "in": int(input_tokens or 0), "out": int(output_tokens or 0), "cached": int(cached or 0),
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
    return {"model_calls": len(calls), "failed_calls": len(failed),
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
    return "AI use in this check: %d model call%s, %s tokens in and %s out%s.%s" % (
        totals["model_calls"], "" if totals["model_calls"] == 1 else "s", format(totals["input_tokens"], ","), format(totals["output_tokens"], ","), money, shared)


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
