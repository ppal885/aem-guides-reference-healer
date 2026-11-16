# Streaming, explained from the start

Written on 16 Nov 2026 for someone who has not used streaming before. It explains what streaming is, which of three related things this project does, and the code that does it, line by line.

## 1. What streaming is

When you ask a model a question, the answer is produced a few words at a time. There are two ways to receive it.

- **Without streaming:** the server keeps every word until the answer is complete, then sends it in one piece. Your program waits and sees nothing. Like ordering a meal and getting every dish at once at the end.
- **With streaming:** the server sends each small piece as soon as it exists. Your program receives many small messages over one open connection. Like the dishes arriving one by one.

The answer is the same either way. What changes is when the bytes travel.

## 2. Why it matters, even when nobody watches

Two reasons, and only the second applies to this project.

1. **A person is watching.** A chat window shows the words as they arrive, so the wait feels short.
2. **The connection must stay alive.** A long answer can take minutes. Without streaming, nothing travels during that time, and a proxy, a load balancer or the client itself may decide the connection is dead and cut it. With streaming, small pieces keep arriving, so nothing times out.

Our agents ask for answers of up to 16,000 tokens with thinking. Nobody reads them while they arrive; they are JSON for the program. We stream for reason 2.

## 3. Three things that are easy to mix up

| Name | What it is | In this project |
|---|---|---|
| Polling | The browser asks "any news?" again and again | **Yes.** The panel asks AEM every 1.5 s what the agents are doing and shows the list of steps. |
| Streaming a model request | One model call delivers its answer in pieces | **Yes, since 16 Nov 2026**, for the API backend only. |
| Streaming results to the user | Repairs appear in the panel one by one while the check runs | **No.** The health check job in AEM waits for the whole answer of the agents. |

So the live list an author sees during a check is polling, not streaming.

## 4. The code

All of it is in `claudeapi.py`. Three small functions call each other: `call_model` → `_create` → `_send` → `_stream`.

### Before

```python
return client().beta.messages.create(**request)
```

One call. It returns when the whole answer is there.

### After

```python
def _stream(**request):
    with client().beta.messages.stream(**request) as stream:
        return stream.get_final_message()
```

Line by line:

- `client()` gives the Anthropic SDK client. It reads the key from the environment; the key is never in a file.
- `.beta.messages.stream(**request)` opens a streaming request. `**request` passes on whatever the caller asked for: model, system prompt, messages, tools.
- `with ... as stream:` keeps the connection open inside the block and closes it afterwards, also when an error happens. This is why `with` is used and not a plain call.
- `stream.get_final_message()` reads every piece as it arrives, puts them together, and returns one complete message. It is the same kind of object `create` returned.

That last point is why nothing else in the project had to change. The agents still get one finished message. The pieces are collected for them.

### The function around it

```python
def _send(**request):
    global _fallbacks_supported
    if _fallbacks_supported:
        try:
            return _stream(betas=[FALLBACK_BETA], fallbacks="default", **request)
        except anthropic.BadRequestError as exc:
            if "fallback" not in str(exc).lower():
                raise
            _fallbacks_supported = False
    return _stream(**request)
```

- It first tries the request with an extra option (`fallbacks`).
- Some endpoints do not know that option and answer "bad request". Then it remembers that (`_fallbacks_supported = False`) and sends the request again without it.
- Any other bad request is a real error and is passed on (`raise`).

### And the one that counts

```python
def _create(**request):
    try:
        response = _send(**request)
    except Exception as exc:
        usage.note(False, error=exc)
        raise
    usage.note(True, *usage.tokens_of(response.usage), cached=usage.cached_of(response.usage))
    return response
```

- Every call is noted in `usage.py`: a failed one with its error, a good one with its tokens.
- The token counts come from the final message, so they are complete even though the answer arrived in pieces.

## 5. If you wanted to show the words as they arrive

We do not, but this is what it would look like:

```python
with client().messages.stream(model="claude-opus-5-5", max_tokens=1000,
                              messages=[{"role": "user", "content": "Say hello"}]) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

`stream.text_stream` hands you each piece of text. `flush=True` makes the terminal show it at once.

## 6. How to try it

The default backend is the `claude` CLI, which does not stream. To use the API backend, set the key in your own terminal (never in a file, never in a chat) and start the sidecar like this:

```bash
.venv/bin/python sidecar.py --serve 8766 --backend sdk
```

Then run a health check. The result looks the same; the difference is that a long answer no longer risks a timeout.

## 7. How to see that streaming is on

Three ways, from quick to sure.

1. **Ask the sidecar.**

   ```bash
   curl -s http://127.0.0.1:8766/health
   ```

   `{"status": "ok", "backend": "cli", "streaming": false}` means the `claude` CLI is used: no streaming. With `--backend sdk` it says `"backend": "sdk", "streaming": true`, and after the first model call also `"last_stream": {"first_piece_seconds": 0.9, "pieces": 142, "seconds": 12.4}`.

2. **Read the log.** With the API backend every model call writes one line to `out/sidecar.log`:

   ```
   stream: first piece after 0.9 s, 142 pieces, done after 12.4 s
   ```

3. **Read those numbers.** This is the proof. With streaming the first piece comes early and many pieces follow, so "first piece after" is much smaller than "done after". Without streaming there would be one piece at the very end, and the two times would be the same.

(The numbers above are made up to show the shape.)

**Measured on 16 Nov 2026**, with the owner's key in the owner's terminal and the sidecar on `--backend sdk`: one request with the eight references of `samples/hard-demo` was answered in 27 s, and `/health` then said `"last_stream": {"first_piece_seconds": 4.52, "pieces": 35, "seconds": 5.43}`. So the last model call delivered 35 pieces, the first after 4.5 s and the last after 5.4 s. The long wait before the first piece is the model thinking; the answer itself then arrived over about a second.

## 8. What was tested, and what was not

- Tested: two unit tests with a stand-in client (`TheApiBackendStreams` in `tests/test_refs.py`). They check that the answer is the whole message, that tokens are counted, and that a request is sent again without `fallbacks` when the endpoint refuses it.
- Checked: the installed SDK (0.125.0) takes the same parameters for `stream` as for `create`.
- Tested against the live API once, on 16 Nov 2026 (see section 7): all eight references of `samples/hard-demo` got the right target. Not measured there: cost, and the large sample.

## 9. Mistakes beginners make

- Calling `stream(...)` without `with`. The connection is then not closed when something fails.
- Reading the stream twice. Once the pieces are read they are gone; keep the final message.
- Expecting the answer to be better or faster. It is the same answer in the same time. Only the delivery changes.
- Calling polling "streaming". Asking every 1.5 s is many short requests; streaming is one long one.
