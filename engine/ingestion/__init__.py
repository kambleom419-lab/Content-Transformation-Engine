from engine.ingestion import documents, image, media, ocr, text as text_parser, web
from engine.ingestion.chunking import chunk_blocks
from engine.ingestion.language import detect_language, normalize_to_english
from engine.ingestion.types import IngestedSource, SourceBlock
from engine.llm import LLMProvider

DOC_EXTS = (".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".md", ".txt")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")

SOURCE_TYPE_HINTS = {
    "advisory": "advisory",
    "incident": "incident",
    "policy": "policy",
    "research": "research",
    "paper": "research",
    "announcement": "announcement",
    "report": "report",
    "article": "article",
}


def infer_kind(source_input: dict) -> str:
    explicit = source_input.get("kind")
    if explicit:
        return explicit
    if source_input.get("url"):
        return "url"
    filename = (source_input.get("filename") or "").lower()
    if filename.endswith(DOC_EXTS):
        return "document"
    if filename.endswith(IMAGE_EXTS):
        return "image"
    if media.is_media_file(filename):
        return "media"
    if source_input.get("data") or source_input.get("path"):
        return "document"
    return "text"


def infer_source_type(source_input: dict, kind: str) -> str:
    explicit = source_input.get("source_type")
    if explicit:
        return explicit
    haystack = f"{source_input.get('filename', '')} {source_input.get('id', '')}".lower()
    for needle, label in SOURCE_TYPE_HINTS.items():
        if needle in haystack:
            return label
    return {"url": "article", "image": "image", "media": "transcript"}.get(kind, "report")


def ingest(source_input: dict, llm: LLMProvider) -> IngestedSource:
    kind = infer_kind(source_input)
    filename = source_input.get("filename") or ""
    source_id = source_input.get("id") or filename or "source"
    name = filename or source_id
    meta: dict = {}
    warnings: list[str] = []

    if kind == "text":
        blocks = text_parser.parse_text(source_input.get("text", ""), name)
    elif kind == "url":
        url = source_input["url"]
        blocks, title = web.fetch_url(url)
        meta["url"] = url
        meta["title"] = title
        name = url
    elif kind == "document":
        blocks, doc_meta = documents.parse_document(
            source_input.get("data"), source_input.get("path"), filename or "document.pdf", name
        )
        blocks, ocr_meta = ocr.ocr_fallback(
            source_input.get("data"),
            source_input.get("path"),
            filename or "",
            name,
            llm,
            blocks,
            doc_meta,
        )
        meta.update(doc_meta)
        meta.update(ocr_meta)
        if ocr_meta.get("ocr_applied"):
            warnings.append(
                f"text layer was thin ({ocr_meta.get('ocr_reason')}); OCR'd {ocr_meta.get('ocr_pages')} page(s)"
            )
        if ocr_meta.get("figures"):
            extra = ocr_meta.get("figures_skipped")
            suffix = f" ({extra} skipped over cap)" if extra else ""
            warnings.append(f"described {ocr_meta['figures']} embedded figure(s){suffix}")
        for key, label in (("ocr_error", "OCR"), ("figure_error", "figure")):
            if ocr_meta.get(key):
                warnings.append(f"{label} fallback failed: {ocr_meta[key]}")
    elif kind == "image":
        blocks = image.parse_image(
            llm,
            name,
            data=source_input.get("data"),
            path=source_input.get("path"),
            mime_type=source_input.get("mime_type"),
        )
        meta["ocr"] = True
    elif kind == "media":
        path = source_input.get("path")
        if not path:
            raise ValueError("media ingestion requires a local file 'path'")
        blocks = media.transcribe_media(llm, name, path, source_input.get("mime_type"))
        meta["transcribed"] = True
    else:
        raise ValueError(f"unknown source kind: {kind!r}")

    raw_text = "\n\n".join(b.text for b in blocks)
    language = detect_language(raw_text)
    blocks, translated = normalize_to_english(blocks, llm, language, warnings)
    if translated:
        meta["translated_to_english"] = True

    for block in blocks:
        if not block.source_id:
            block.source_id = source_id

    blocks = chunk_blocks(blocks)
    meta["block_count"] = len(blocks)

    return IngestedSource(
        source_id=source_id,
        kind=kind,
        source_type=infer_source_type(source_input, kind),
        language=language,
        blocks=blocks,
        title=meta.get("title"),
        meta=meta,
        warnings=warnings,
    )


def _dedupe_ids(sources: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    resolved: list[dict] = []
    for index, source in enumerate(sources, start=1):
        raw_id = source.get("id") or source.get("filename") or f"source-{index}"
        name = str(raw_id)
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        resolved.append({**source, "id": name})
    return resolved


def ingest_sources(sources: list[dict], llm: LLMProvider) -> tuple[list[dict], list[dict], list[str]]:
    corpus: list[dict] = []
    descriptors: list[dict] = []
    warnings: list[str] = []

    for source in _dedupe_ids(sources):
        try:
            ingested = ingest(source, llm)
        except Exception as exc:
            warnings.append(f"source '{source.get('id')}' failed to ingest: {exc}")
            continue
        corpus.extend(ingested.corpus())
        descriptors.append(ingested.descriptor())
        warnings.extend(f"{ingested.source_id}: {w}" for w in ingested.warnings)

    if not corpus:
        raise ValueError("no source content could be ingested")

    return corpus, descriptors, warnings


__all__ = [
    "IngestedSource",
    "SourceBlock",
    "chunk_blocks",
    "detect_language",
    "infer_kind",
    "infer_source_type",
    "ingest",
    "ingest_sources",
]
