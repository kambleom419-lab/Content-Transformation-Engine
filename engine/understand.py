"""
The "understand" step of the pipeline.

Turns a cleaned corpus (list of {text, source_ref, ...} chunks) into ONE
structured content_model that every downstream artefact is generated from.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from engine.llm import LLMProvider
from engine.llm_utils import (
    DEFAULT_MAX_ATTEMPTS,
    MIN_TOKEN_OVERLAP_FOR_GROUNDING,
    dedupe_strings,
    generate_json_with_retry,
)
from engine.llm_utils import tokens as _tokens
from engine.recipes import (
    CONTENT_MODEL_SCHEMA,
    build_understand_prompt,
    repair_content_model,
)

DEFAULT_MAX_CHARS_PER_BATCH = 9000

_IPV4 = r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
_DOMAIN = r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,24})\b"
_URL = r"\bhttps?://[^\s\]\)\"'<>]+"
_HASH = r"\b[a-f0-9]{32}\b|\b[a-f0-9]{40}\b|\b[a-f0-9]{64}\b"
_CVE = r"\bCVE-\d{4}-\d{4,7}\b"
_EMAIL = r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"

IOC_PATTERNS = [
    ("cve", re.compile(_CVE, re.IGNORECASE)),
    ("url", re.compile(_URL, re.IGNORECASE)),
    ("hash", re.compile(_HASH, re.IGNORECASE)),
    ("email", re.compile(_EMAIL, re.IGNORECASE)),
    ("ipv4", re.compile(_IPV4)),
    ("domain", re.compile(_DOMAIN, re.IGNORECASE)),
]

_DOMAIN_STOPWORDS = {
    "e.g.com", "i.e.com", "etc.com", "fig.com", "vs.com", "no.com",
}

# Real TLDs only. PDF table extraction glues cells together, producing strings
# like "minutes.Thetraveltimesused" — the domain pattern matches these happily
# because ".The" looks like a TLD. Requiring a plausible TLD drops them.
_COMMON_TLDS = frozenset(
    """
    com org net edu gov mil int io co ai app dev cloud tech info biz online site xyz
    me tv uk de fr jp cn in au ca br ru it nl se no es ch at be dk fi pl cz gr pt ie
    nz za sg hk kr tw th vn id ph my mx ar cl pe tr il sa ae pk bd lk np
    """.split()
)


def _plausible_domain(value: str) -> bool:
    return value.rsplit(".", 1)[-1].lower() in _COMMON_TLDS


def extract_iocs_regex(text: str) -> list[str]:
    """Deterministic IOC extraction used as a safety net alongside the model."""
    found: list[str] = []
    seen: set[str] = set()

    consumed_spans: list[tuple[int, int]] = []
    for _, pattern in ((k, p) for k, p in IOC_PATTERNS if k in ("cve", "url", "hash", "email")):
        for m in pattern.finditer(text):
            value = m.group(0).rstrip(".,;:)")
            key = value.lower()
            if key not in seen:
                seen.add(key)
                found.append(value)
            consumed_spans.append(m.span())

    def _in_consumed(pos: int) -> bool:
        return any(start <= pos < end for start, end in consumed_spans)

    for kind, pattern in ((k, p) for k, p in IOC_PATTERNS if k in ("ipv4", "domain")):
        for m in pattern.finditer(text):
            if _in_consumed(m.start()):
                continue
            value = m.group(0).rstrip(".,;:)")
            key = value.lower()
            if key in _DOMAIN_STOPWORDS or key in seen:
                continue
            if kind == "domain" and not _plausible_domain(value):
                continue
            seen.add(key)
            found.append(value)

    return found


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def dedupe_facts(facts: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for fact in facts:
        text = str(fact.get("text") or "").strip()
        if not text:
            continue
        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "source_ref": str(fact.get("source_ref") or "").strip()})
    return out


def batch_corpus(corpus: list[dict], max_chars: int = DEFAULT_MAX_CHARS_PER_BATCH) -> list[list[dict]]:
    """Group corpus chunks into batches that each stay under max_chars."""
    if not corpus:
        return []
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0
    for chunk in corpus:
        chunk_len = len(chunk.get("text", ""))
        if current and current_len + chunk_len > max_chars:
            batches.append(current)
            current, current_len = [], 0
        current.append(chunk)
        current_len += chunk_len
    if current:
        batches.append(current)
    return batches


@dataclass
class GroundingResult:
    grounded: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    repaired_refs: int = 0


def ground_facts(facts: list[dict], corpus: list[dict]) -> GroundingResult:
    """
    Verify every fact actually traces back to the corpus by word overlap —
    a syntactically valid source_ref is not enough, since the model can cite
    a real chunk while still writing a claim that chunk doesn't support.
    """
    corpus_tokens = [(_tokens(c["text"]), c["source_ref"]) for c in corpus]

    result = GroundingResult()
    for fact in facts:
        cited_ref = str(fact.get("source_ref") or "").strip()
        text = str(fact.get("text") or "").strip()
        if not text:
            continue

        fact_tokens = _tokens(text)
        best_score, best_ref = 0, None
        for ctokens, cref in corpus_tokens:
            score = len(fact_tokens & ctokens)
            if score > best_score:
                best_score, best_ref = score, cref

        if best_ref and best_score >= MIN_TOKEN_OVERLAP_FOR_GROUNDING:
            result.grounded.append({"text": text, "source_ref": best_ref})
            if best_ref != cited_ref:
                result.repaired_refs += 1
        else:
            result.dropped.append({"text": text, "source_ref": cited_ref or None})

    return result


_generate_with_retry = generate_json_with_retry


MERGE_INSTRUCTIONS = """You are merging several PARTIAL content models — each built from a
different slice of the same source document(s) — into ONE final content model.

Rules:
- Combine facts from all partials. Keep each fact's original source_ref exactly as given.
- Do not invent any new facts, numbers, dates, IPs, hashes or IoCs beyond what's in the partials.
- Merge iocs, timeline, entities, key_messages and recommended_actions across all partials,
  removing duplicates and near-duplicates.
- Pick (or write) ONE title that best represents the whole document.
- Pick the HIGHEST severity found across the partials (info < low < medium < high < critical).
- Return a single JSON object only (no markdown fences, no commentary).
"""


def build_merge_prompt(partials: list[dict]) -> str:
    blocks = "\n\n".join(f"--- PARTIAL {i + 1} ---\n{json.dumps(p, ensure_ascii=False)}" for i, p in enumerate(partials))
    return f"{MERGE_INSTRUCTIONS}\n=== PARTIAL CONTENT MODELS ===\n{blocks}\n=== END PARTIALS ==="


def run_understand(
    corpus: list[dict],
    source_input: dict,
    sources: list[dict] | None = None,
    llm: LLMProvider | None = None,
    max_chars_per_batch: int = DEFAULT_MAX_CHARS_PER_BATCH,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    if llm is None:
        raise ValueError("run_understand requires an llm provider")
    if not corpus:
        raise ValueError("run_understand requires a non-empty corpus")

    sources = sources or []
    fallback_source_type = source_input.get("source_type", "report")
    fallback_language = source_input.get("source_language", "en")

    batches = batch_corpus(corpus, max_chars_per_batch)
    total_retries = 0

    if len(batches) <= 1:
        prompt = build_understand_prompt(corpus, source_input, sources)
        raw, attempts = _generate_with_retry(llm, prompt, CONTENT_MODEL_SCHEMA, max_attempts)
        total_retries += attempts - 1
        merged_raw = raw
    else:
        partials = []
        for batch in batches:
            prompt = build_understand_prompt(batch, source_input, sources)
            raw, attempts = _generate_with_retry(llm, prompt, CONTENT_MODEL_SCHEMA, max_attempts)
            total_retries += attempts - 1
            partials.append(repair_content_model(raw, fallback_source_type, fallback_language))

        merge_prompt = build_merge_prompt(partials)
        merged_raw, attempts = _generate_with_retry(llm, merge_prompt, CONTENT_MODEL_SCHEMA, max_attempts)
        total_retries += attempts - 1

    model = repair_content_model(merged_raw, fallback_source_type, fallback_language)

    full_text = "\n".join(c["text"] for c in corpus)
    regex_iocs = extract_iocs_regex(full_text)
    model["iocs"] = dedupe_strings(list(model.get("iocs", [])) + regex_iocs)

    model["entities"] = dedupe_strings(model.get("entities", []))
    model["timeline"] = dedupe_strings(model.get("timeline", []))
    model["key_messages"] = dedupe_strings(model.get("key_messages", []))
    model["recommended_actions"] = dedupe_strings(model.get("recommended_actions", []))

    facts = dedupe_facts(model.get("facts", []))
    grounding = ground_facts(facts, corpus)
    model["facts"] = grounding.grounded

    model["_meta"] = {
        "batches": len(batches),
        "retries": total_retries,
        "facts_extracted": len(facts),
        "facts_grounded": len(grounding.grounded),
        "facts_dropped_ungrounded": len(grounding.dropped),
        "facts_ref_repaired": grounding.repaired_refs,
        "dropped_facts_preview": [f["text"][:120] for f in grounding.dropped[:5]],
        "regex_iocs_found": len(regex_iocs),
    }

    return model