from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict, right: dict) -> dict:
    merged = dict(left)
    merged.update(right)
    return merged


class EngineState(TypedDict):
    source_input: dict
    corpus: list[dict]
    content_model: dict
    selected_outputs: list[str]
    artefact_type: str | None
    artefacts: Annotated[dict, merge_dicts]
    fact_checks: Annotated[dict, merge_dicts]
    review: dict | None
    export: dict | None


def empty_state(source_input: dict, selected_outputs: list[str]) -> dict:
    return {
        "source_input": source_input,
        "corpus": [],
        "content_model": {},
        "selected_outputs": selected_outputs,
        "artefact_type": None,
        "artefacts": {},
        "fact_checks": {},
        "review": None,
        "export": None,
    }
