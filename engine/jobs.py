"""
In-memory registry of engine runs.

The LangGraph checkpointer holds the actual graph state; this registry is the
bookkeeping the HTTP layer needs to answer "what is this run doing?" without
touching the checkpointer on every request.

Deliberately process-local: a restart loses run history. Swap in a persistent
store (or the SqliteSaver checkpointer) when the audit trail matters.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

RUNNING = "running"
AWAITING_REVIEW = "awaiting_review"
COMPLETE = "complete"
FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Run:
    thread_id: str
    label: str = ""
    status: str = RUNNING
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    snapshot: dict = field(default_factory=dict)
    review_request: dict | None = None
    error: str | None = None

    def summary(self) -> dict:
        artefacts = self.snapshot.get("artefacts") or {}
        return {
            "thread_id": self.thread_id,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "artefact_types": sorted(artefacts),
            "title": (self.snapshot.get("content_model") or {}).get("title", ""),
            "error": self.error,
        }

    def detail(self) -> dict:
        return {
            **self.summary(),
            "content_model": self.snapshot.get("content_model") or {},
            "artefacts": self.snapshot.get("artefacts") or {},
            "fact_checks": self.snapshot.get("fact_checks") or {},
            "export": self.snapshot.get("export"),
            "review": self.snapshot.get("review"),
            "review_request": self.review_request,
            "sources": self.snapshot.get("sources") or [],
            "warnings": (self.snapshot.get("source_input") or {}).get("warnings", []),
        }


class JobRegistry:
    """Thread-safe run registry — FastAPI runs sync handlers on a threadpool."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}

    def add(self, run: Run) -> Run:
        with self._lock:
            self._runs[run.thread_id] = run
        return run

    def get(self, thread_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(thread_id)

    def update(self, thread_id: str, **fields) -> Run | None:
        with self._lock:
            run = self._runs.get(thread_id)
            if run is None:
                return None
            for key, value in fields.items():
                setattr(run, key, value)
            run.updated_at = _now()
            return run

    def list(self) -> list[Run]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)


__all__ = [
    "AWAITING_REVIEW",
    "COMPLETE",
    "FAILED",
    "RUNNING",
    "JobRegistry",
    "Run",
]
