"""
The "generate_and_check" step — runs once per selected output type, inside
each fan_out branch, and does the actual drafting + verification work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from engine.llm import LLMProvider
from engine.llm_utils import (
    DEFAULT_MAX_ATTEMPTS,
    MIN_TOKEN_OVERLAP_FOR_GROUNDING,
    generate_json_with_retry,
    normalise_tree,
    tokens,
)
from engine.recipes import ARTEFACT_PROFILES, build_generation_prompt
from engine.understand import extract_iocs_regex

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
# A bare "1" is usually a list or scene number, not a claim. Only treat a number
# as factual if it carries a unit ("9 hours"), or has two or more digits ("72").
NUMBER_UNITS = (
    r"(?:hours?|days?|minutes?|seconds?|weeks?|months?|years?|percent|%|million|billion|"
    r"thousand|kb|mb|gb|tb|users?|hosts?|servers?|systems?|organi[sz]ations?|customers?|"
    r"records?|files?|accounts?|devices?|endpoints?|machines?|assets?|attacks?)"
)
NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(" + NUMBER_UNITS + r")?", re.IGNORECASE)
MIN_SUPPORT_RATIO = 0.6
MAX_REGENERATION_PASSES = 1

# X's Web Intent refuses to prefill a post longer than 280 characters, so an
# over-long tweet silently loses the "open in X" redirect. The prompt asks the
# model to stay inside the limit; this enforces it when the model overshoots.
X_TWEET_LIMIT = 280

_ARRAY_FIELDS = {
    "affected_systems", "iocs", "mitigations", "references",
    "key_points", "recommendations", "hashtags", "tweets",
    "storyboard", "scene_descriptions", "subtitles", "visual_recommendations",
    "content", "layout_recommendations", "key_messaging",
}

_SLIDE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "speaker_notes": {"type": "string"},
    },
    "required": ["title"],
}


def build_artefact_json_schema(artefact_type: str) -> dict:
    profile = ARTEFACT_PROFILES[artefact_type]
    properties: dict[str, Any] = {}
    for field_name in profile["fields"]:
        if field_name == "slides":
            properties[field_name] = {"type": "array", "items": _SLIDE_ITEM_SCHEMA}
        elif field_name in _ARRAY_FIELDS:
            properties[field_name] = {"type": "array", "items": {"type": "string"}}
        else:
            properties[field_name] = {"type": "string"}
    return {"type": "object", "properties": properties, "required": profile["fields"]}


def clamp_tweet(text: str, limit: int = X_TWEET_LIMIT) -> str:
    """
    Hold one tweet inside X's character limit.

    Clamping happens at a word boundary and marks the cut with an ellipsis, so
    the post stays readable and the "open in X" redirect keeps working. Only the
    final tweet that overflows is shortened; the thread keeps every other post.
    """
    text = str(text).strip()
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rstrip()
    space = clipped.rfind(" ")
    if space > 0:
        clipped = clipped[:space].rstrip()
    return f"{clipped}…"


def _clamp_x_thread(draft: dict) -> dict:
    tweets = draft.get("tweets")
    if isinstance(tweets, list):
        draft = {**draft, "tweets": [clamp_tweet(tweet) for tweet in tweets]}
    return draft


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.extend(_flatten_text(list(item.values())))
            else:
                parts.extend(_flatten_text(item))
        return parts
    return []


def _extract_sentences(draft: dict) -> list[str]:
    sentences = []
    for piece in _flatten_text(list(draft.values())):
        for sentence in SENTENCE_RE.split(str(piece)):
            sentence = sentence.strip()
            if 20 < len(sentence) < 600:
                sentences.append(sentence)
    return sentences


@dataclass
class FactCheckResult:
    verdicts: list[dict] = field(default_factory=list)
    supported: int = 0
    unsupported: int = 0
    unverified: int = 0

    @property
    def support_ratio(self) -> float:
        total = self.supported + self.unsupported + self.unverified
        return 1.0 if total == 0 else self.supported / total


def numbers(text: str) -> set[str]:
    """
    Factual numbers in a piece of text: quantities with units, dates, versions,
    percentages. Token overlap can never catch a changed number, because "72"
    and "9" are both just short tokens.

    Bare single digits are skipped — "Scene 1" or "1/6" is structure, not a claim.
    """
    found: set[str] = set()
    for raw, unit in NUMBER_RE.findall(text or ""):
        cleaned = raw.strip(".,")
        if not cleaned:
            continue
        if unit or len(cleaned.replace(",", "").replace(".", "")) >= 2:
            found.add(cleaned)
    return found


def fact_check_draft(draft: dict, corpus: list[dict]) -> FactCheckResult:
    entries = [(tokens(c["text"]), numbers(c["text"]), c["source_ref"]) for c in corpus]
    known_numbers: set[str] = set().union(*(nums for _, nums, _ in entries)) if entries else set()
    result = FactCheckResult()

    for sentence in _extract_sentences(draft):
        sentence_tokens = tokens(sentence)
        best_score, best_ref = 0, None
        for ctokens, _cnumbers, cref in entries:
            score = len(sentence_tokens & ctokens)
            if score > best_score:
                best_score, best_ref = score, cref

        if not (best_score >= MIN_TOKEN_OVERLAP_FOR_GROUNDING and best_ref):
            result.verdicts.append({"claim": sentence, "verdict": "unsupported", "citation": None})
            result.unsupported += 1
            continue

        invented = numbers(sentence) - known_numbers
        if invented:
            result.verdicts.append(
                {
                    "claim": sentence,
                    "verdict": "unverified_number",
                    "citation": best_ref,
                    "unverified_numbers": sorted(invented),
                }
            )
            result.unverified += 1
        else:
            result.verdicts.append({"claim": sentence, "verdict": "supported", "citation": best_ref})
            result.supported += 1

    return result


def check_ioc_integrity(draft: dict, verified_iocs: list[str]) -> list[dict]:
    """Flag any IOC-shaped string in the draft that wasn't in the verified content model."""
    verified_lower = {ioc.lower() for ioc in verified_iocs}
    full_text = " ".join(_flatten_text(list(draft.values())))
    found = extract_iocs_regex(full_text)

    unverified = []
    for ioc in found:
        if ioc.lower() not in verified_lower:
            unverified.append({"claim": ioc, "verdict": "unverified_ioc", "citation": None})
    return unverified


def _missing_fields(draft: dict, required_fields: list[str]) -> list[str]:
    return [f for f in required_fields if not draft.get(f)]


def _repair_missing_fields(
    llm: LLMProvider,
    artefact_type: str,
    content_model: dict,
    params: dict,
    draft: dict,
    missing: list[str],
    max_attempts: int,
) -> dict:
    schema = build_artefact_json_schema(artefact_type)
    base_prompt = build_generation_prompt(artefact_type, content_model, params)
    repair_prompt = (
        f"{base_prompt}\n\n"
        "=== REPAIR REQUEST ===\n"
        f"Your previous draft was missing these required fields: {', '.join(missing)}.\n"
        f"Here is your previous draft so far: {draft}\n"
        "Return the COMPLETE artefact again as a single JSON object with every "
        "required field filled in, including the ones already present above.\n"
    )
    repaired, _ = generate_json_with_retry(llm, repair_prompt, schema, max_attempts)
    return repaired


def _regenerate_with_feedback(
    llm: LLMProvider,
    artefact_type: str,
    content_model: dict,
    params: dict,
    unsupported_claims: list[str],
    max_attempts: int,
) -> dict:
    schema = build_artefact_json_schema(artefact_type)
    base_prompt = build_generation_prompt(artefact_type, content_model, params)
    examples = "\n".join(f"- {c}" for c in unsupported_claims[:5])
    feedback_prompt = (
        f"{base_prompt}\n\n"
        "=== GROUNDING FEEDBACK ===\n"
        "Your previous draft included claims that could not be verified against the source "
        "content model. Do not repeat claims like these; use ONLY facts, entities, iocs, "
        "timeline entries and key_messages present in the content model above:\n"
        f"{examples}\n"
    )
    draft, _ = generate_json_with_retry(llm, feedback_prompt, schema, max_attempts)
    return draft


def run_generate_and_check(
    artefact_type: str,
    content_model: dict,
    corpus: list[dict],
    params: dict | None = None,
    llm: LLMProvider | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_support_ratio: float = MIN_SUPPORT_RATIO,
) -> dict:
    if llm is None:
        raise ValueError("run_generate_and_check requires an llm provider")
    if artefact_type not in ARTEFACT_PROFILES:
        raise ValueError(f"unknown artefact_type: {artefact_type!r}")

    params = params or {}
    profile = ARTEFACT_PROFILES[artefact_type]
    schema = build_artefact_json_schema(artefact_type)

    prompt = build_generation_prompt(artefact_type, content_model, params)
    raw, attempts = generate_json_with_retry(llm, prompt, schema, max_attempts)
    draft = {k: raw.get(k) for k in profile["fields"] if raw.get(k) is not None}
    total_retries = attempts - 1

    missing = _missing_fields(draft, profile["fields"])
    fields_repaired = False
    if missing:
        repaired_raw = _repair_missing_fields(
            llm, artefact_type, content_model, params, draft, missing, max_attempts
        )
        for f in missing:
            if repaired_raw.get(f) is not None:
                draft[f] = repaired_raw[f]
        fields_repaired = True
        missing = _missing_fields(draft, profile["fields"])

    if artefact_type == "x_thread":
        draft = _clamp_x_thread(draft)

    fact_check = fact_check_draft(draft, corpus)
    regenerated = False

    if fact_check.support_ratio < min_support_ratio and MAX_REGENERATION_PASSES > 0:
        unsupported_claims = [v["claim"] for v in fact_check.verdicts if v["verdict"] != "supported"]
        new_raw = _regenerate_with_feedback(
            llm, artefact_type, content_model, params, unsupported_claims, max_attempts
        )
        new_draft = {k: new_raw.get(k) for k in profile["fields"] if new_raw.get(k) is not None}
        if artefact_type == "x_thread":
            new_draft = _clamp_x_thread(new_draft)
        new_fact_check = fact_check_draft(new_draft, corpus)

        if new_fact_check.support_ratio > fact_check.support_ratio:
            draft = new_draft
            fact_check = new_fact_check
            regenerated = True
            missing = _missing_fields(draft, profile["fields"])

    ioc_flags = check_ioc_integrity(draft, content_model.get("iocs", []))
    verdicts = fact_check.verdicts + ioc_flags

    meta = {
        "retries": total_retries,
        "fields_repaired": fields_repaired,
        "missing_fields": missing,
        "regenerated_for_grounding": regenerated,
        "sentences_checked": fact_check.supported + fact_check.unsupported + fact_check.unverified,
        "sentences_supported": fact_check.supported,
        "sentences_unsupported": fact_check.unsupported,
        "sentences_unverified": fact_check.unverified,
        "unverified_numbers": sorted(
            {
                value
                for verdict in fact_check.verdicts
                for value in verdict.get("unverified_numbers", [])
            }
        ),
        "support_ratio": round(fact_check.support_ratio, 3),
        "unverified_iocs": [f["claim"] for f in ioc_flags],
    }

    return {"draft": normalise_tree(draft), "verdicts": verdicts, "meta": meta}