"""The Claude API behind the agents (Anthropic SDK), used with --backend sdk (garage-week PoC).

Needs the `anthropic` package and credentials in the environment (ANTHROPIC_API_KEY, or
ANTHROPIC_AUTH_TOKEN). Set them in your own terminal; never write them into a file.
"""
import os
import threading

import anthropic

import sidecar

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client = None
_client_lock = threading.Lock()
# Set to False the first time the endpoint rejects the `fallbacks` parameter (a gateway or a
# cloud platform that does not support it), so later requests go without it.
_fallbacks_supported = os.environ.get("REFHEAL_FALLBACKS", "on") != "off"


def client():
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


def _create(**request):
    """One Messages request. Opts in to server-side refusal fallback, and drops it for the rest of
    the run if this endpoint does not accept the parameter."""
    global _fallbacks_supported
    if _fallbacks_supported:
        try:
            return client().beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request)
        except anthropic.BadRequestError as exc:
            if "fallback" not in str(exc).lower():
                raise
            _fallbacks_supported = False
    return client().beta.messages.create(**request)


def call_model(system, user, model=None):
    """One request that must answer with a JSON object."""
    response = _create(
        model=model or MODEL,
        max_tokens=16000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined this request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The model's answer was cut off")
    return sidecar.parse_json("".join(block.text for block in response.content if block.type == "text"))
