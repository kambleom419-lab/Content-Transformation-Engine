import hashlib
import json
import re
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from engine.ingestion import ingest_sources
from engine.llm import LLMProvider, StubAdapter
from engine.recipes import ARTEFACT_PROFILES
from engine.render import write_artefact_files
from engine.state import EngineState
from engine.understand import run_understand
from engine.generate import run_generate_and_check

WORD_RE = re.compile(r"[a-z0-9]{3,}")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _resolve_sources(state: EngineState) -> list[dict]:
    sources = state.get("sources") or []
    if sources:
        return list(sources)
    source_input = state.get("source_input") or {}
    if source_input:
        return [source_input]
    return []


def ingest_source(state: EngineState, llm: LLMProvider) -> dict:
    sources = _resolve_sources(state)
    if not sources:
        raise ValueError("no sources provided in state")

    corpus, descriptors, warnings = ingest_sources(sources, llm)
    primary = descriptors[0]
    languages = sorted({d["language"] for d in descriptors})
    source_types = [d["source_type"] for d in descriptors]

    return {
        "corpus": corpus,
        "sources": descriptors,
        "source_input": {
            **(state.get("source_input") or {}),
            "id": primary["source_id"],
            "kind": primary["kind"] if len(descriptors) == 1 else "multi",
            "source_type": source_types[0] if len(source_types) == 1 else "multi",
            "source_language": languages[0] if len(languages) == 1 else "mixed",
            "warnings": warnings,
        },
    }


def clean_parse(state: EngineState) -> dict:
    seen: set[str] = set()
    cleaned = []
    for chunk in state["corpus"]:
        normalized = re.sub(r"\s+", " ", chunk["text"]).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            entry = {"text": normalized, "source_ref": chunk["source_ref"]}
            if chunk.get("kind"):
                entry["kind"] = chunk["kind"]
            if chunk.get("source_id"):
                entry["source_id"] = chunk["source_id"]
            cleaned.append(entry)
    return {"corpus": cleaned}


def understand(state: EngineState, llm: LLMProvider) -> dict:
    content_model = run_understand(
        corpus=state["corpus"],
        source_input=state["source_input"],
        sources=state.get("sources") or [],
        llm=llm,
    )
    return {"content_model": content_model}


def _branch_payload(state: EngineState, artefact_type: str) -> dict:
    return {
        "artefact_type": artefact_type,
        "source_input": state["source_input"],
        "corpus": state["corpus"],
        "content_model": state["content_model"],
        "selected_outputs": state["selected_outputs"],
    }


def fan_out(state: EngineState) -> list[Send]:
    return [Send("generate_and_check", _branch_payload(state, t)) for t in state["selected_outputs"]]


def fan_out_affected(state: EngineState) -> list[Send]:
    review = state["review"] or {}
    types = review.get("types") or state["selected_outputs"]
    return [Send("generate_and_check", _branch_payload(state, t)) for t in types]


def generate_and_check(state: EngineState, llm: LLMProvider) -> dict:
    artefact_type = state["artefact_type"]
    params = {k: state["source_input"].get(k) for k in ("target_audience", "tone", "language")}
    result = run_generate_and_check(
        artefact_type=artefact_type,
        content_model=state["content_model"],
        corpus=state["corpus"],
        params=params,
        llm=llm,
    )
    return {
        "artefacts": {artefact_type: result["draft"]},
        "fact_checks": {artefact_type: {"verdicts": result["verdicts"], "meta": result["meta"]}},
    }


def human_review(state: EngineState) -> dict:
    payload = {
        "artefacts": state["artefacts"],
        "fact_checks": state["fact_checks"],
        "content_model": {k: state["content_model"].get(k) for k in ("title", "severity", "key_messages")},
    }
    decision = interrupt(payload)
    return {"review": decision}


def route_review(state: EngineState) -> str:
    action = (state.get("review") or {}).get("action", "refine")
    return "accept" if action == "accept" else "refine"


def apply_feedback(state: EngineState, llm: LLMProvider) -> dict:
    review = state["review"]
    instruction = review.get("instruction", "")
    content_model = dict(state["content_model"])
    directives = content_model.get("operator_directives", [])
    if instruction:
        directives.append(instruction)
    content_model["operator_directives"] = directives
    return {"content_model": content_model}


def guardrails_render(state: EngineState) -> dict:
    run_id = state["source_input"].get("run_id") or state["source_input"].get("id") or "run"

    validated = []
    for artefact_type, draft in state["artefacts"].items():
        profile = ARTEFACT_PROFILES[artefact_type]
        missing = [k for k in profile["fields"] if not draft.get(k)]
        digest = hashlib.sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest()
        validated.append({"type": artefact_type, "valid": not missing, "missing_fields": missing, "sha256": digest})

    try:
        files = write_artefact_files(run_id, state["artefacts"], state["content_model"])
        render_error = None
    except Exception as exc:  # rendering is a filesystem boundary — never lose a finished run to it
        files = []
        render_error = f"{type(exc).__name__}: {exc}"

    export = {
        "status": "ready" if files else "empty",
        "run_id": run_id,
        "artefacts": validated,
        "files": files,
        "render_error": render_error,
        "source": state["source_input"].get("id"),
        "sources": [s.get("source_id") for s in state.get("sources", [])],
        "model": state["content_model"].get("title"),
    }
    return {"export": export}


def build_graph(llm: LLMProvider | None = None) -> Any:
    provider = llm or StubAdapter()

    def ingest_source_node(state: EngineState) -> dict:
        return ingest_source(state, provider)

    def understand_node(state: EngineState) -> dict:
        return understand(state, provider)

    def generate_and_check_node(state: EngineState) -> dict:
        return generate_and_check(state, provider)

    def apply_feedback_node(state: EngineState) -> dict:
        return apply_feedback(state, provider)

    graph = StateGraph(EngineState)
    graph.add_node("ingest_source", ingest_source_node)
    graph.add_node("clean_parse", clean_parse)
    graph.add_node("understand", understand_node)
    graph.add_node("generate_and_check", generate_and_check_node)
    graph.add_node("human_review", human_review)
    graph.add_node("apply_feedback", apply_feedback_node)
    graph.add_node("guardrails_render", guardrails_render)

    graph.add_edge(START, "ingest_source")
    graph.add_edge("ingest_source", "clean_parse")
    graph.add_edge("clean_parse", "understand")
    graph.add_conditional_edges("understand", fan_out, ["generate_and_check"])
    graph.add_edge("generate_and_check", "human_review")
    graph.add_conditional_edges("human_review", route_review, {"accept": "guardrails_render", "refine": "apply_feedback"})
    graph.add_conditional_edges("apply_feedback", fan_out_affected, ["generate_and_check"])
    graph.add_edge("guardrails_render", END)

    return graph.compile(checkpointer=MemorySaver())