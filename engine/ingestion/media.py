from engine.ingestion.chunking import split_paragraphs
from engine.ingestion.types import SourceBlock
from engine.llm import AUDIO_EXTS, VIDEO_EXTS, LLMProvider, MediaPart, guess_mime

TRANSCRIBE_PROMPT = """Transcribe this media recording into clear English text.

- Capture all spoken content faithfully; keep names, numbers, dates, IP addresses
  and identifiers exact.
- Insert a [timestamp] marker (mm:ss) at each topic change.
- If the recording is not in English, produce the English translation.
- Do not summarise or add commentary.
Return plain text only."""


def is_media_file(filename: str) -> bool:
    lower = (filename or "").lower()
    suffix = lower[lower.rfind(".") :] if "." in lower else ""
    return suffix in VIDEO_EXTS or suffix in AUDIO_EXTS


def transcribe_media(
    llm: LLMProvider,
    name: str,
    path: str,
    mime_type: str | None = None,
) -> list[SourceBlock]:
    mime = mime_type or guess_mime(path)
    part = MediaPart(mime_type=mime, path=path)
    text = llm.generate_text(TRANSCRIBE_PROMPT, parts=[part])
    return [
        SourceBlock(text=para, ref=f"{name} {i:02d}", kind="transcript")
        for i, para in enumerate(split_paragraphs(text or ""), start=1)
    ]
