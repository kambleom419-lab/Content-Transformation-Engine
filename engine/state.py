from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict, right: dict) -> dict:
    merged = dict(left)
    merged.update(right)
    return merged


class EngineState(TypedDict):
    source_input: dict
    sources: list[dict]
    corpus: list[dict]
    content_model: dict
    selected_outputs: list[str]
    artefact_type: str | None
    artefacts: Annotated[dict, merge_dicts]
    fact_checks: Annotated[dict, merge_dicts]
    review: dict | None
    export: dict | None


def empty_state(
    source_input: dict | None = None,
    selected_outputs: list[str] | None = None,
    sources: list[dict] | None = None,
) -> dict:
    return {
        "source_input": source_input or {},
        "sources": sources or [],
        "corpus": [],
        "content_model": {},
        "selected_outputs": selected_outputs or [],
        "artefact_type": None,
        "artefacts": {},
        "fact_checks": {},
        "review": None,
        "export": None,
    }
