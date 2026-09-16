"""
Optional LangSmith tracing — agent/graph observability.

OFF unless explicitly enabled, and that default is deliberate: turning it on
exports prompts, model outputs and graph state to a third-party service. For a
controlled environment keep it off and rely on engine/usage.py, which gives the
local numbers without any data leaving the machine.

Enable:

    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=ls__...
    LANGSMITH_PROJECT=content-engine

What you get:

- **Graph/agent traces** come free once tracing is on: LangGraph reports every
  node execution (`ingest_source`, `clean_parse`, `understand`,
  `generate_and_check` per branch, `human_review`, `guardrails_render`) with its
  state in/out, so the fan-out, the pause and the refine loop are all visible.
- **LLM spans** are added by `@traced_llm` on the provider adapters, one run per
  model call.

Secrets never reach the tracer: `self` is deliberately not passed into the
traced call, so the adapter's API key cannot be serialised into a trace.
"""

from __future__ import annotations

import os
from functools import wraps

from engine import config  # noqa: F401  - loads .env before langsmith reads it

TRUTHY = {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    """
    Tracing is active only when it is switched on AND a key exists.

    Without the key check, LangSmith would accept the decorated calls and then
    fail every background upload with a 401 — filling the console with auth
    errors for what is really a configuration mistake.
    """
    if os.getenv("LANGSMITH_TRACING", "false").strip().lower() not in TRUTHY:
        return False
    return bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))


def tracing_status() -> dict:
    """Describe the current tracing setup — surfaced by GET /health."""
    return {
        "enabled": tracing_enabled(),
        "project": os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default",
        "endpoint": os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com",
        "has_api_key": bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")),
    }


def traced_llm(operation: str):
    """
    Decorate an adapter method so each model call becomes a LangSmith LLM span.

    A no-op when tracing is off, so the decorator can be applied unconditionally.

    Only the prompt and schema are handed to the tracer. `self` — which holds the
    API key — and the media parts (raw bytes) stay out of the recorded inputs;
    their size is captured as metadata instead.
    """

    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if not tracing_enabled():
                return method(self, *args, **kwargs)

            try:
                from langsmith import traceable
            except ImportError:
                return method(self, *args, **kwargs)

            prompt = args[0] if args else kwargs.get("prompt", "")
            parts = kwargs.get("parts")

            @traceable(
                run_type="llm",
                name=f"{self.name}.{operation}",
                metadata={
                    "provider": self.name,
                    "model": getattr(self, "model", None),
                    "vision_model": getattr(self, "vision_model", None),
                    "operation": operation,
                    "media_parts": len(parts or []),
                    "has_schema": kwargs.get("json_schema") is not None,
                    "prompt_chars": len(prompt or ""),
                },
            )
            def _call(text: str):
                # `self` and the media parts stay out of the traced inputs —
                # self holds the API key, and parts hold raw image/audio bytes.
                return method(self, *args, **kwargs)

            return _call(prompt)

        return wrapper

    return decorator


__all__ = ["traced_llm", "tracing_enabled", "tracing_status"]
