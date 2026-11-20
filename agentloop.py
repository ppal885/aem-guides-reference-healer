"""One tool-using agent loop with two model backends (garage-week PoC).

    "sdk": the Claude API through the Anthropic SDK, with native tool use.
    "cli": the local `claude` CLI; the model writes one JSON action per step.

Both run the same tools and end with the same `finish` arguments, so the code that checks the
answer does not care which one produced it.

A tool is a dict: {"name", "description", "properties", "required", "fn"}; fn(args) returns a
JSON-serialisable observation. `finish` is described the same way, without fn.
"""
import json

MAX_RESULT_CHARS = 16000


def run(system, task, tools, finish, backend="cli", model=None, max_calls=8, log=None):
    """Returns (finish arguments or None, steps, problem). problem is None on a normal finish."""
    log = log or (lambda message: None)
    if backend == "sdk":
        return _run_sdk(system, task, tools, finish, model, max_calls, log)
    return _run_cli(system, task, tools, finish, model, max_calls, log)


def _log_call(response, steps, log):
    """One line per model call: what it read (and how much of that came from the prompt cache), what it
    wrote, and the biggest tool result it carries. To see where an agent's tokens go."""
    use = getattr(response, "usage", None)
    if use is None:
        return
    fresh, read, written = (int(getattr(use, k, 0) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                                     "cache_creation_input_tokens"))
    biggest = max(steps, key=lambda step: step.get("chars", 0), default=None)
    log("    model call: %d in (%d read from the cache, %d written to it), %d out; %d tool results so far, %d chars%s" % (
        fresh + read + written, read, written, int(getattr(use, "output_tokens", 0) or 0), len(steps),
        sum(step.get("chars", 0) for step in steps),
        ", biggest %s %d" % (biggest["tool"], biggest["chars"]) if biggest else ""))


def _summary(observation):
    if isinstance(observation, dict) and observation.get("summary"):
        return str(observation["summary"])[:120]
    return json.dumps(observation, ensure_ascii=False)[:120]


def _call_tool(tool, args, steps, log):
    try:
        observation = tool["fn"](args)
        failed = False
    except Exception as exc:  # a tool failure is an observation for the model, not a crash
        observation, failed = {"error": "tool failed: %s" % str(exc)[:200]}, True
    text = json.dumps(observation, ensure_ascii=False)
    steps.append({"tool": tool["name"], "args": args, "result": _summary(observation),
                  "chars": min(len(text), MAX_RESULT_CHARS)})     # how much of the next calls' context it is
    log("    step %d %-13s %s -> %s" % (len(steps), tool["name"], json.dumps(args, ensure_ascii=False)[:70],
                                         _summary(observation)[:70]))
    return text[:MAX_RESULT_CHARS], failed


def _coerce(spec, value):
    """A value written as loose JSON by the CLI model, in the type the tool declares: a number
    where a string is expected, one string where a list is."""
    kind = spec.get("type")
    if value is None:
        return [] if kind == "array" else ""
    if kind == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if kind == "array":
        items = value if isinstance(value, list) else [value]
        return [item if isinstance(item, str) else json.dumps(item, ensure_ascii=False) for item in items]
    return value


def _valid(spec, args):
    if not isinstance(args, dict):
        return False
    for name in spec["required"]:
        if name not in args:
            return False
    for name, value in args.items():
        kind = spec["properties"].get(name, {}).get("type")
        if kind == "string" and not isinstance(value, str):
            return False
        if kind == "array" and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            return False
    return True


# ---- Claude API ----------------------------------------------------------------------------

def _run_sdk(system, task, tools, finish, model, max_calls, log):
    import anthropic
    import claudeapi

    by_name = {t["name"]: t for t in tools}
    specs = [{"name": t["name"], "description": t["description"], "strict": True,
              "input_schema": {"type": "object", "properties": t["properties"], "required": t["required"],
                               "additionalProperties": False}} for t in tools + [finish]]
    messages = [{"role": "user", "content": task + "\n\nYou may make up to %d tool calls before finish." % max_calls}]
    steps, calls = [], 0
    for _ in range(max_calls + 4):
        try:
            response = claudeapi._create(
                model=model or claudeapi.MODEL, max_tokens=16000, system=system, tools=specs,
                thinking={"type": "adaptive"}, output_config={"effort": "high"},
                cache_control={"type": "ephemeral"}, messages=messages)
        except TypeError as exc:
            if "authentication" not in str(exc).lower():
                raise
            return None, steps, "No Claude API credentials are set."
        except anthropic.AuthenticationError:
            return None, steps, "Could not sign in to the Claude API."
        except anthropic.PermissionDeniedError:
            return None, steps, "The Claude API credentials lack permission for this model."
        except anthropic.NotFoundError:
            return None, steps, "The Claude API did not recognise the model or endpoint."
        except anthropic.RateLimitError:
            return None, steps, "The Claude API rate limit was reached."
        except anthropic.APIStatusError as exc:
            return None, steps, "The Claude API returned an error (HTTP %s)." % exc.status_code
        except anthropic.APIConnectionError:
            return None, steps, "The Claude API could not be reached."
        _log_call(response, steps, log)
        if response.stop_reason == "refusal":
            return None, steps, "The model declined this request."
        if response.stop_reason == "max_tokens":
            return None, steps, "The model's answer was cut off."

        uses = [block for block in response.content if block.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})
        if not uses:
            messages.append({"role": "user", "content": "Call the finish tool with your answer."})
            continue
        results = []
        for block in uses:
            if block.name == finish["name"]:
                if _valid(finish, block.input):
                    return block.input, steps, None
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "Invalid finish input."})
                continue
            tool = by_name.get(block.name)
            if tool is None or not _valid(tool, block.input):
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "Unknown tool or invalid input."})
                continue
            calls += 1
            if calls > max_calls:
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "No tool calls left. Call finish now."})
                continue
            content, failed = _call_tool(tool, block.input, steps, log)
            result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
            if failed:
                result["is_error"] = True
            results.append(result)
        left = max_calls - calls
        results.append({"type": "text", "text": "Tool calls left: %d.%s" % (max(left, 0), " Call finish now." if left <= 0 else "")})
        messages.append({"role": "user", "content": results})
    return None, steps, "No answer within the turn limit."


# ---- claude CLI ----------------------------------------------------------------------------

def _protocol(tools, finish):
    lines = ["", "You work in steps. In each step reply with one JSON object and nothing else.", "", "Tools:"]
    for tool in tools:
        args = ", ".join('"%s": <%s>' % (name, spec.get("type", "string")) for name, spec in tool["properties"].items())
        lines.append('- {"action": "%s"%s} — %s' % (tool["name"], ", " + args if args else "", tool["description"]))
    # The whole description: it carries the format of the answer, and cutting it loses fields.
    args = ", ".join('"%s": <%s>' % (name, spec.get("description", spec.get("type", "string")))
                     for name, spec in finish["properties"].items())
    lines += ["", "Finish with:", '{"action": "%s", %s}' % (finish["name"], args)]
    return "\n".join(lines)


def _run_cli(system, task, tools, finish, model, max_calls, log):
    import sidecar

    by_name = {t["name"]: t for t in tools}
    transcript, steps = [task], []
    full_system = system + _protocol(tools, finish)
    for step in range(1, max_calls + 2):
        left = max_calls + 1 - step
        prompt = "\n\n".join(transcript) + "\n\nTool calls left: %d.%s" % (left, " You must finish now." if left == 0 else "")
        try:
            action = sidecar.call_model(full_system, prompt, model)
        except Exception as exc:
            return None, steps, "The agent stopped: %s" % str(exc)[:160]
        name = action.pop("action", None)
        action.pop("thought", None)
        if name == finish["name"]:
            for key in finish["required"]:
                action.setdefault(key, "")
            action = {k: _coerce(finish["properties"].get(k, {}), v) for k, v in action.items()}
            return (action, steps, None) if _valid(finish, action) else (None, steps, "The agent's answer was malformed.")
        tool = by_name.get(name)
        if tool is None or left == 0:
            transcript.append("Step %d: unknown or unavailable action %r. Finish now." % (step, name))
            continue
        for key, spec in tool["properties"].items():
            action.setdefault(key, [] if spec.get("type") == "array" else "")
        if not _valid(tool, action):
            wanted = ", ".join("%s (%s)" % (key, spec.get("type", "string")) for key, spec in tool["properties"].items())
            transcript.append("Step %d: invalid input for %s. It takes: %s. Try again." % (step, name, wanted or "nothing"))
            continue
        content, _ = _call_tool(tool, action, steps, log)
        transcript.append("Step %d: you called %s %s\nResult: %s" % (step, name, json.dumps(action, ensure_ascii=False), content))
    return None, steps, "No answer within %d steps." % max_calls
