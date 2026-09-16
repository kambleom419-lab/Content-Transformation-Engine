"""
Local token and latency ledger.

Observability that always works: no SaaS, no network, no API key. It complements
LangSmith tracing (which is opt-in, see engine/tracing.py) so the numbers are
still available in a controlled environment, in offline runs, and under the stub
provider.

Every provider call goes through `track()`, which records what was asked of
which model, how long it took, whether it failed, and — where the provider
reports it — how many tokens it cost.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass

RECENT_LIMIT = 25


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def openai_usage(payload: dict) -> tuple[int, int]:
    """Token counts from an OpenAI-compatible response body."""
    usage = (payload or {}).get("usage") or {}
    return _to_int(usage.get("prompt_tokens")), _to_int(usage.get("completion_tokens"))


def gemini_usage(response) -> tuple[int, int]:
    """Token counts from a google-genai response."""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return 0, 0
    return (
        _to_int(getattr(metadata, "prompt_token_count", 0)),
        _to_int(getattr(metadata, "candidates_token_count", 0)),
    )


@dataclass
class Entry:
    provider: str
    model: str
    operation: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ok: bool = True


class Ledger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[Entry] = []

    def add(self, entry: Entry) -> None:
        with self._lock:
            self._entries.append(entry)

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()

    def snapshot(self) -> dict:
        with self._lock:
            entries = list(self._entries)

        by_provider: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
        )
        by_operation: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
        )

        for entry in entries:
            for bucket, key in ((by_provider, entry.provider), (by_operation, entry.operation)):
                row = bucket[key]
                row["calls"] += 1
                row["errors"] += 0 if entry.ok else 1
                row["prompt_tokens"] += entry.prompt_tokens
                row["completion_tokens"] += entry.completion_tokens
                row["latency_ms"] += entry.latency_ms

        return {
            "calls": len(entries),
            "errors": sum(0 if entry.ok else 1 for entry in entries),
            "prompt_tokens": sum(entry.prompt_tokens for entry in entries),
            "completion_tokens": sum(entry.completion_tokens for entry in entries),
            "total_tokens": sum(entry.prompt_tokens + entry.completion_tokens for entry in entries),
            "latency_ms": sum(entry.latency_ms for entry in entries),
            "by_provider": dict(by_provider),
            "by_operation": dict(by_operation),
            "recent": [asdict(entry) for entry in entries[-RECENT_LIMIT:]],
        }


LEDGER = Ledger()


@contextmanager
def track(provider: str, model: str, operation: str):
    """
    Time a provider call and record it — whether it succeeds or raises.

    The caller sets token counts on the yielded entry once the response is
    available:

        with track("groq", "gpt-oss-120b", "generate_json") as entry:
            payload = post(...)
            entry.prompt_tokens, entry.completion_tokens = openai_usage(payload)
    """
    entry = Entry(provider=provider, model=model, operation=operation)
    started = time.perf_counter()
    try:
        yield entry
    except Exception:
        entry.ok = False
        raise
    finally:
        entry.latency_ms = int((time.perf_counter() - started) * 1000)
        LEDGER.add(entry)


__all__ = ["Entry", "LEDGER", "Ledger", "gemini_usage", "openai_usage", "track"]
