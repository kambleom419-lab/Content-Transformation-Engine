from engine.ingestion.types import SourceBlock
from engine.llm import LLMProvider

MIN_SAMPLE_CHARS = 20
MAX_TRANSLATE_BLOCKS = 60

TRANSLATE_PROMPT = """Translate the following text into clear, professional English.
Preserve names, numbers, dates, IP addresses, hashes and technical identifiers exactly.
Return ONLY the translation, with no commentary or markdown fences.

=== TEXT ===
{text}
=== END TEXT ==="""


def detect_language(text: str) -> str:
    sample = (text or "").strip()
    if len(sample) < MIN_SAMPLE_CHARS:
        return "unknown"
    try:
        from langdetect import detect

        return detect(sample[:2000])
    except Exception:
        return "unknown"


def normalize_to_english(
    blocks: list[SourceBlock],
    llm: LLMProvider,
    language: str,
    warnings: list[str],
) -> tuple[list[SourceBlock], bool]:
    if language in ("en", "unknown") or not blocks:
        return blocks, False

    if not hasattr(llm, "generate_text"):
        warnings.append(f"source language '{language}' but provider cannot translate")
        return blocks, False

    if len(blocks) > MAX_TRANSLATE_BLOCKS:
        warnings.append(
            f"source has {len(blocks)} blocks; translating first {MAX_TRANSLATE_BLOCKS} to limit cost"
        )
        blocks = blocks[:MAX_TRANSLATE_BLOCKS]

    translated: list[SourceBlock] = []
    for block in blocks:
        try:
            text = llm.generate_text(TRANSLATE_PROMPT.format(text=block.text)).strip()
        except Exception as exc:
            warnings.append(f"translation failed for {block.ref}: {exc}")
            text = block.text
        translated.append(
            SourceBlock(text=text, ref=block.ref, kind=block.kind, page=block.page, heading=block.heading)
        )
    return translated, True
