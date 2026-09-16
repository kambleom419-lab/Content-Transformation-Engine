"""
HTTP layer for the content transformation engine.

    uvicorn engine.api:app --port 8000

The graph is compiled exactly once at import time: the checkpointer keeps its
state inside the compiled graph object, so rebuilding the graph per request
would make `resume` fail with a missing checkpoint.

The graph itself is synchronous and can run for minutes (Docling + model
calls), so every invocation is dispatched to a thread pool and the caller
polls GET /run/{thread_id}.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from engine.config import get_artefacts_dir, get_cors_origins, get_use_stub
from engine.graph import build_graph
from engine.jobs import AWAITING_REVIEW, COMPLETE, FAILED, RUNNING, JobRegistry, Run
from engine.llm import StubAdapter
from engine.providers import build_llm_provider
from engine.recipes import ARTEFACT_PROFILES
from engine.state import empty_state
from engine.tracing import tracing_status
from engine.usage import LEDGER

OUTPUT_TYPES = sorted(ARTEFACT_PROFILES)

MEDIA_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".srt": "application/x-subrip",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

PROVIDER = StubAdapter() if get_use_stub() else build_llm_provider()
GRAPH = build_graph(PROVIDER)
REGISTRY = JobRegistry()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="engine-run")


class SourceSpec(BaseModel):
    id: str | None = None
    kind: str | None = None
    text: str | None = None
    url: str | None = None
    path: str | None = None
    data_base64: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    source_type: str | None = None


class RunRequest(BaseModel):
    sources: list[SourceSpec] = Field(default_factory=list)
    selected_outputs: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    label: str = ""


class ResumeRequest(BaseModel):
    action: str = "accept"
    instruction: str = ""
    types: list[str] = Field(default_factory=list)


app = FastAPI(title="Content Transformation Engine", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_outputs(types: list[str]) -> list[str]:
    if not types:
        raise HTTPException(400, f"selected_outputs must not be empty (choose from: {', '.join(OUTPUT_TYPES)})")
    unknown = [t for t in types if t not in ARTEFACT_PROFILES]
    if unknown:
        raise HTTPException(400, f"unknown artefact type(s): {', '.join(unknown)}")
    return list(dict.fromkeys(types))


def _write_upload(thread_id: str, filename: str, data: bytes) -> Path:
    folder = get_artefacts_dir() / "uploads" / thread_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(filename or "source.bin").name
    target.write_bytes(data)
    return target


def _to_engine_source(spec: SourceSpec, thread_id: str) -> dict:
    source: dict = {}
    for key in ("id", "kind", "mime_type", "source_type"):
        value = getattr(spec, key)
        if value:
            source[key] = value

    if spec.text:
        source["text"] = spec.text
        return source
    if spec.url:
        source["url"] = spec.url
        return source
    if spec.data_base64:
        try:
            data = base64.b64decode(spec.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(400, f"source {spec.filename or spec.id!r}: invalid data_base64 ({exc})")
        path = _write_upload(thread_id, spec.filename or "upload.bin", data)
        source["path"] = str(path)
        source["filename"] = spec.filename or path.name
        return source
    if spec.path:
        source["path"] = spec.path
        source["filename"] = spec.filename or Path(spec.path).name
        return source

    raise HTTPException(400, "each source needs one of: text, url, path, data_base64")


def _record_snapshot(thread_id: str, snapshot: dict) -> None:
    interrupts = snapshot.get("__interrupt__") or ()
    clean = {k: v for k, v in snapshot.items() if k != "__interrupt__"}
    if interrupts:
        request = getattr(interrupts[0], "value", None) or {}
        REGISTRY.update(
            thread_id, status=AWAITING_REVIEW, snapshot=clean, review_request=request, error=None
        )
    else:
        REGISTRY.update(thread_id, status=COMPLETE, snapshot=clean, review_request=None, error=None)


def _run_graph(thread_id: str, state: dict | None, decision: dict | None) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        if decision is None:
            snapshot = GRAPH.invoke(state, config)
        else:
            snapshot = GRAPH.invoke(Command(resume=decision), config)
    except Exception as exc:
        REGISTRY.update(thread_id, status=FAILED, error=f"{type(exc).__name__}: {exc}")
        return
    _record_snapshot(thread_id, snapshot)


def _require_run(thread_id: str) -> Run:
    run = REGISTRY.get(thread_id)
    if run is None:
        raise HTTPException(404, f"unknown run: {thread_id}")
    return run


def _start(thread_id: str, sources: list[dict], outputs: list[str], params: dict, label: str) -> Run:
    run = REGISTRY.add(Run(thread_id=thread_id, label=label, status=RUNNING))
    state = empty_state(
        {
            **params,
            "id": thread_id,
            "run_id": thread_id,
            "kind": sources[0].get("kind") if len(sources) == 1 else "multi",
        },
        outputs,
        sources,
    )
    EXECUTOR.submit(_run_graph, thread_id, state, None)
    return run


@app.get("/health")
def health() -> dict:
    chain = [provider.name for provider in getattr(PROVIDER, "providers", [])] or [PROVIDER.name]
    return {
        "status": "ok",
        "provider": PROVIDER.name,
        "chain": chain,
        "last_used": getattr(PROVIDER, "last_used", None),
        "cooldowns": getattr(PROVIDER, "events", []),
        "tracing": tracing_status(),
        "outputs": OUTPUT_TYPES,
        "runs": len(REGISTRY.list()),
    }


@app.get("/usage")
def usage() -> dict:
    """
    Token, latency and error accounting for every provider call this process made.

    Works with or without LangSmith: this is the local, always-on view, so the
    numbers are still available in an air-gapped deployment.
    """
    return LEDGER.snapshot()


@app.post("/usage/reset")
def reset_usage() -> dict:
    """Clear the ledger — useful for measuring a single demo run cleanly."""
    LEDGER.reset()
    return {"status": "reset"}


@app.post("/run", status_code=202)
def start_run(request: RunRequest) -> dict:
    outputs = _validate_outputs(request.selected_outputs)
    if not request.sources:
        raise HTTPException(400, "at least one source is required")

    thread_id = uuid.uuid4().hex[:12]
    sources = [_to_engine_source(spec, thread_id) for spec in request.sources]
    label = request.label or (sources[0].get("filename") or sources[0].get("url") or "text source")
    run = _start(thread_id, sources, outputs, request.params, label)
    return {"thread_id": run.thread_id, "status": run.status, "label": run.label}


@app.post("/run/upload", status_code=202)
async def start_run_upload(payload: str = Form("{}"), files: list[UploadFile] = File(default=[])) -> dict:
    try:
        body = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"payload must be JSON: {exc}")

    request = RunRequest.model_validate(body)
    outputs = _validate_outputs(request.selected_outputs)
    thread_id = uuid.uuid4().hex[:12]

    sources = [_to_engine_source(spec, thread_id) for spec in request.sources]
    for upload in files:
        data = await upload.read()
        if not data:
            continue
        path = _write_upload(thread_id, upload.filename or "upload.bin", data)
        sources.append(
            {
                "path": str(path),
                "filename": upload.filename or path.name,
                "mime_type": upload.content_type or None,
            }
        )

    if not sources:
        raise HTTPException(400, "no sources: upload at least one file or include a text/url source")

    label = request.label or (files[0].filename if files else sources[0].get("url") or "text source")
    run = _start(thread_id, sources, outputs, request.params, label)
    return {"thread_id": run.thread_id, "status": run.status, "label": run.label}


@app.get("/runs")
def list_runs() -> list[dict]:
    return [run.summary() for run in REGISTRY.list()]


@app.get("/run/{thread_id}")
def get_run(thread_id: str) -> dict:
    return _require_run(thread_id).detail()


@app.post("/run/{thread_id}/resume", status_code=202)
def resume_run(thread_id: str, request: ResumeRequest) -> dict:
    run = _require_run(thread_id)
    if run.status == RUNNING:
        raise HTTPException(409, "run is still working; poll GET /run/{thread_id} first")
    if run.status == FAILED:
        raise HTTPException(409, f"run failed and cannot be resumed: {run.error}")
    if run.status == COMPLETE:
        raise HTTPException(409, "run is already complete")

    action = (request.action or "").strip().lower()
    if action not in {"accept", "refine"}:
        raise HTTPException(400, "action must be 'accept' or 'refine'")

    decision: dict = {"action": action}
    if action == "refine":
        if not request.instruction.strip():
            raise HTTPException(400, "refine requires an instruction")
        decision["instruction"] = request.instruction
        decision["types"] = _validate_outputs(request.types or [])
        REGISTRY.update(thread_id, status=RUNNING)
        EXECUTOR.submit(_run_graph, thread_id, None, decision)
    else:
        REGISTRY.update(thread_id, status=RUNNING)
        EXECUTOR.submit(_run_graph, thread_id, None, decision)

    return {"thread_id": thread_id, "status": RUNNING, "action": action}


@app.get("/run/{thread_id}/artefacts/{artefact_type}/download")
def download_artefact(thread_id: str, artefact_type: str, ext: str | None = None):
    run = _require_run(thread_id)
    export = run.snapshot.get("export") or {}
    files = [f for f in export.get("files", []) if f.get("type") == artefact_type]
    if ext:
        files = [f for f in files if f.get("ext") == ext]
    if not files:
        raise HTTPException(404, f"no exported file for {artefact_type!r} on this run")

    path = Path(files[0].get("path") or "")
    if not path.is_file():
        raise HTTPException(404, f"exported file is missing on disk: {path}")
    return FileResponse(path, filename=path.name, media_type=MEDIA_TYPES.get(path.suffix, "application/octet-stream"))


if __name__ == "__main__":
    import uvicorn

    from engine.config import get_api_host, get_api_port

    uvicorn.run("engine.api:app", host=get_api_host(), port=get_api_port())
