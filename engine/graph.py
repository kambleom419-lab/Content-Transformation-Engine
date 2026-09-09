import hashlib
import json
import re
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from engine.llm import LLMProvider, StubAdapter
from engine.recipes import ARTEFACT_PROFILES, CONTENT_MODEL_SCHEMA, build_generation_prompt, build_understand_prompt
from engine.state import EngineState

WORD_RE = re.compile(r"[a-z0-9]{3,}")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def ingest_source(state: EngineState) -> dict:
    src = state["source_input"]
    text = src.get("text", "")
    kind = src.get("kind", "text")
    source_id = src.get("id", "doc1")
    raw_chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    corpus = [{"text": c, "source_ref": f"{source_id} §{i + 1}"} for i, c in enumerate(raw_chunks)]
    return {"corpus": corpus, "source_input": {**src, "kind": kind, "id": source_id}}


def clean_parse(state: EngineState) -> dict:
    seen: set[str] = set()
    cleaned = []
    for chunk in state["corpus"]:
        normalized = re.sub(r"\s+", " ", chunk["text"]).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append({"text": normalized, "source_ref": chunk["source_ref"]})
    return {"corpus": cleaned}


def understand(state: EngineState, llm: LLMProvider) -> dict:
    prompt = build_understand_prompt(state["corpus"])
    content_model = llm.generate_json(prompt, json_schema=CONTENT_MODEL_SCHEMA)
    content_model.setdefault("facts", [])
    content_model.setdefault("key_messages", [])
    content_model.setdefault("recommended_actions", [])
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


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.extend(_flatten_text(list(item.values())))
            else:
                parts.extend(_flatten_text(item))
        return parts
    return []


def _tokens(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def generate_and_check(state: EngineState, llm: LLMProvider) -> dict:
    artefact_type = state["artefact_type"]
    profile = ARTEFACT_PROFILES[artefact_type]
    params = {k: state["source_input"].get(k) for k in ("target_audience", "tone", "language")}
    prompt = build_generation_prompt(artefact_type, state["content_model"], params)
    draft = llm.generate_json(prompt)
    draft = {k: draft.get(k) for k in profile["fields"] if draft.get(k) is not None}

    chunks = [(c["text"], c["source_ref"]) for c in state["corpus"]]
    corpus_tokens = [_tokens(t) for t, _ in chunks]
    sentences = []
    for piece in _flatten_text(list(draft.values())):
        for sentence in SENTENCE_RE.split(str(piece)):
            sentence = sentence.strip()
            if 20 < len(sentence) < 600:
                sentences.append(sentence)

    verdicts = []
    for sentence in sentences:
        tokens = _tokens(sentence)
        best_score, best_ref = 0, None
        for idx, ctokens in enumerate(corpus_tokens):
            score = len(tokens & ctokens)
            if score > best_score:
                best_score, best_ref = score, chunks[idx][1]
        if best_score >= 3 and best_ref:
            verdicts.append({"claim": sentence, "verdict": "supported", "citation": best_ref})
        else:
            verdicts.append({"claim": sentence, "verdict": "unsupported", "citation": None})

    return {"artefacts": {artefact_type: draft}, "fact_checks": {artefact_type: verdicts}}


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
    files = []
    validated = []
    for artefact_type, draft in state["artefacts"].items():
        profile = ARTEFACT_PROFILES[artefact_type]
        missing = [k for k in profile["fields"] if not draft.get(k)]
        digest = hashlib.sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest()
        validated.append({"type": artefact_type, "valid": not missing, "missing_fields": missing, "sha256": digest})
        files.append({"type": artefact_type, "ext": profile["export_ext"], "sha256": digest})
    export = {
        "status": "ready",
        "artefacts": validated,
        "files": files,
        "source": state["source_input"].get("id"),
        "model": state["content_model"].get("title"),
    }
    return {"export": export}


def build_graph(llm: LLMProvider | None = None) -> Any:
    provider = llm or StubAdapter()

    def understand_node(state: EngineState) -> dict:
        return understand(state, provider)

    def generate_and_check_node(state: EngineState) -> dict:
        return generate_and_check(state, provider)

    def apply_feedback_node(state: EngineState) -> dict:
        return apply_feedback(state, provider)

    graph = StateGraph(EngineState)
    graph.add_node("ingest_source", ingest_source)
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
