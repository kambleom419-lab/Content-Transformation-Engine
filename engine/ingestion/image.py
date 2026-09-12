from engine.ingestion.chunking import split_paragraphs
from engine.ingestion.types import SourceBlock
from engine.llm import LLMProvider, MediaPart, guess_mime

OCR_PROMPT = """You are an OCR and image-analysis engine for an intelligence platform.

1. Transcribe ALL visible text in this image verbatim, preserving numbers, dates,
   IP addresses, hashes and identifiers exactly. Keep reading order.
2. If the image is a chart, diagram or screenshot, add a short factual description
   of what it shows.
3. Do not add commentary, opinions or markdown fences.
Return plain text only."""


def parse_image(
    llm: LLMProvider,
    name: str,
    data: bytes | None = None,
    path: str | None = None,
    mime_type: str | None = None,
) -> list[SourceBlock]:
    mime = mime_type or (guess_mime(path) if path else "image/png")
    part = MediaPart(mime_type=mime, data=data, path=path)
    text = llm.generate_text(OCR_PROMPT, parts=[part])
    return [
        SourceBlock(text=para, ref=f"{name} §{i}", kind="ocr")
        for i, para in enumerate(split_paragraphs(text or ""), start=1)
    ]
