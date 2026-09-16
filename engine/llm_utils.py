"""
Low-level helpers shared by engine/understand.py and engine/generate.py.

Keeping these in one place means "how we retry a failed model call" and
"how we decide a sentence is grounded in the source" are defined exactly
once, so the two pipeline stages can't quietly drift apart.
"""

from __future__ import annotations

import re

from engine.llm import LLMProvider

WORD_RE = re.compile(r"[a-z0-9]{3,}")
MIN_TOKEN_OVERLAP_FOR_GROUNDING = 3
DEFAULT_MAX_ATTEMPTS = 3

# Function words inflate word-overlap scoring: "the vendor recommends patching
# within 72 hours" would otherwise share 5 tokens with almost any sentence on
# the same subject. They must not count as evidence.
STOPWORDS = frozenset(
    """
    about above after again against all also and any are because been before being below
    between both but can did do does doing down during each few for from further had has
    have having her here hers herself him himself his how into its itself just more most
    myself nor not now off once only other others our ours ourselves out over own same she
    should some such than that the their theirs them themselves then there these they this
    those through too under until very was were what when where which while who whom why
    will with would you your yours yourself
    """.split()
)


def tokens(text: str) -> set[str]:
    """Content-bearing tokens only — stopwords are excluded from scoring."""
    return {word for word in WORD_RE.findall((text or "").lower()) if word not in STOPWORDS}


def dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = (item or "").strip()
        if not item:
            continue
        key = re.sub(r"\s+", " ", item.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def generate_json_with_retry(
    llm: LLMProvider,
    prompt: str,
    schema: dict | None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[dict, int]:
    """
    Call llm.generate_json, feeding the error back into the prompt and
    retrying on failure instead of raising immediately.

    Returns (result, attempts_used).
    """
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(1, max_attempts + 1):
        try:
            raw = llm.generate_json(current_prompt, json_schema=schema)
            if not isinstance(raw, dict):
                raise ValueError(f"expected a JSON object, got {type(raw).__name__}")
            return raw, attempt
        except Exception as exc:  # noqa: BLE001 - any failure is worth retrying
            last_error = exc
            current_prompt = (
                f"{prompt}\n\n"
                "=== PREVIOUS ATTEMPT FAILED ===\n"
                f"Error: {exc}\n"
                "Return ONLY a single valid JSON object matching the schema. "
                "No markdown fences, no commentary, no trailing text.\n"
            )
    raise RuntimeError(f"model failed after {max_attempts} attempts: {last_error}")