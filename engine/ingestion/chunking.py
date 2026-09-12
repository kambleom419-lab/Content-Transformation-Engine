import re

from engine.ingestion.types import SourceBlock

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in PARAGRAPH_SPLIT.split(text) if p.strip()]


def merge_refs(refs: list[str]) -> str:
    if not refs:
        return "source"
    if len(refs) == 1:
        return refs[0]
    return f"{refs[0]} … {refs[-1]}"


def _split_long(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    sentences = SENTENCE_SPLIT.split(text)
    pieces: list[str] = []
    buf = ""
    for sentence in sentences:
        if buf and len(buf) + len(sentence) + 1 > max_chars:
            pieces.append(buf.strip())
            tail = buf[-overlap_chars:] if overlap_chars else ""
            buf = (tail + " " + sentence).strip()
        else:
            buf = (buf + " " + sentence).strip() if buf else sentence
    if buf.strip():
        pieces.append(buf.strip())
    return pieces or [text.strip()]


def chunk_blocks(
    blocks: list[SourceBlock],
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[SourceBlock]:
    out: list[SourceBlock] = []
    buf: list[str] = []
    refs: list[str] = []
    buf_source_ids: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, refs, buf_len
        if not buf:
            return
        merged = "\n\n".join(buf)
        if merged:
            out.append(SourceBlock(text=merged, ref=merge_refs(refs), kind="chunk", source_id=buf_source_ids[0] if buf_source_ids else ""))
        buf, refs, buf_len = [], [], 0
        buf_source_ids.clear()

    for block in blocks:
        text = (block.text or "").strip()
        if not text:
            continue

        if block.kind == "heading":
            flush()
            out.append(
                SourceBlock(
                    text=text,
                    ref=block.ref,
                    kind="heading",
                    heading=text,
                    page=block.page,
                    source_id=block.source_id,
                )
            )
            continue

        if len(text) > max_chars:
            flush()
            for i, piece in enumerate(_split_long(text, max_chars, overlap_chars), start=1):
                ref = block.ref if i == 1 else f"{block.ref} (part {i})"
                out.append(
                    SourceBlock(
                        text=piece,
                        ref=ref,
                        kind=block.kind,
                        page=block.page,
                        heading=block.heading,
                        source_id=block.source_id,
                    )
                )
            continue

        if buf_len + len(text) > max_chars:
            flush()

        buf.append(text)
        refs.append(block.ref)
        buf_source_ids.append(block.source_id)
        buf_len += len(text)

    flush()
    return out
