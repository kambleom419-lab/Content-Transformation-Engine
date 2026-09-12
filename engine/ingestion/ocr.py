import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from engine.ingestion.chunking import split_paragraphs
from engine.ingestion.types import SourceBlock
from engine.llm import LLMProvider, MediaPart

MIN_CHARS_PER_PAGE = 250
MIN_PAGE_COVERAGE = 0.6
DEFAULT_MAX_OCR_PAGES = 12
DEFAULT_MAX_FIGURES = 15
DEFAULT_BATCH_SIZE = 4
DEFAULT_BATCH_DELAY_S = 1.0
RENDER_DPI = 150
OCR_WORKERS = 4

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["index", "text"],
            },
        }
    },
    "required": ["results"],
}

OOXML_MEDIA_DIRS = ("word/media/", "ppt/media/", "xl/media/")
OOXML_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp")

VISION_OCR_PROMPT = """Transcribe ALL text visible in this document page image.

- The text may be HANDWRITTEN (lecture notes). Read it as accurately as you can.
- Preserve numbers, symbols and mathematical notation as best you can.
- Keep the natural reading order and separate distinct lines/blocks.
- Ignore scanner watermarks such as "Scanned by CamScanner".
- Do not describe images or add commentary.

Return plain text only."""

FIGURE_PROMPT = """Describe and transcribe this figure from a document.

1. DESCRIPTION: state what the figure shows — chart, graph, diagram, drawing,
   schematic, screenshot or table. For charts mention axes, trends and key values.
   For drawings/schematics describe the structure and its labelled parts.
2. TRANSCRIPTION: transcribe ALL visible text verbatim — labels, legends, part
   codes, cable numbers, table cells, footnotes, annotations.
3. Ignore scanner watermarks such as "Scanned by CamScanner".

Return plain text only, with the description first and the transcription after it."""


def max_ocr_pages() -> int:
    try:
        return int(os.getenv("OCR_MAX_PAGES", DEFAULT_MAX_OCR_PAGES))
    except ValueError:
        return DEFAULT_MAX_OCR_PAGES


def max_figures() -> int:
    try:
        return int(os.getenv("OCR_MAX_FIGURES", DEFAULT_MAX_FIGURES))
    except ValueError:
        return DEFAULT_MAX_FIGURES


def batch_size() -> int:
    try:
        return max(1, int(os.getenv("OCR_BATCH_SIZE", DEFAULT_BATCH_SIZE)))
    except ValueError:
        return DEFAULT_BATCH_SIZE


def batch_delay() -> float:
    try:
        return max(0.0, float(os.getenv("OCR_BATCH_DELAY_S", DEFAULT_BATCH_DELAY_S)))
    except ValueError:
        return DEFAULT_BATCH_DELAY_S


def _read_bytes(data: bytes | None, path: str | None) -> bytes:
    if data is not None:
        return data
    if path:
        with open(path, "rb") as handle:
            return handle.read()
    raise ValueError("ocr needs 'data' or 'path'")


def count_embedded_images(data: bytes | None, path: str | None, filename: str) -> int:
    lower = (filename or "").lower()
    if not lower.endswith((".docx", ".pptx", ".xlsx")):
        return 0
    try:
        buffer = BytesIO(_read_bytes(data, path))
        with zipfile.ZipFile(buffer) as archive:
            return sum(
                1
                for name in archive.namelist()
                if name.startswith(OOXML_MEDIA_DIRS) and name.lower().endswith(OOXML_IMAGE_EXTS)
            )
    except Exception:
        return 0


def document_units(data: bytes | None, path: str | None, filename: str, meta: dict) -> int:
    pages = int(meta.get("pages") or 0)
    if pages > 0:
        return pages
    return max(count_embedded_images(data, path, filename), 1)


def missing_pages(blocks: list[SourceBlock], page_count: int) -> list[int]:
    seen = {b.page for b in blocks if b.page}
    return [page for page in range(1, page_count + 1) if page not in seen]


def chars_per_page(blocks: list[SourceBlock]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for block in blocks:
        if block.page:
            counts[block.page] = counts.get(block.page, 0) + len(block.text or "")
    return counts


def underserved_pages(
    blocks: list[SourceBlock], page_count: int, min_chars: int = MIN_CHARS_PER_PAGE
) -> list[int]:
    """Pages whose text layer is too thin to trust — these need OCR.

    Covers both fully-empty pages and pages carrying only a watermark or a
    handful of stray characters.
    """
    counts = chars_per_page(blocks)
    return [page for page in range(1, page_count + 1) if counts.get(page, 0) < min_chars]


def needs_vision_ocr(blocks: list[SourceBlock], meta: dict, data, path, filename: str) -> tuple[bool, str]:
    pages = int(meta.get("pages") or 0)
    total_chars = sum(len(b.text or "") for b in blocks)

    if pages > 0:
        covered = len({b.page for b in blocks if b.page})
        if covered / pages < MIN_PAGE_COVERAGE:
            return True, f"only {covered}/{pages} pages yielded text"
        if total_chars / pages < MIN_CHARS_PER_PAGE:
            return True, f"only {total_chars // pages} chars/page"
        return False, ""

    units = document_units(data, path, filename, meta)
    if total_chars / units < MIN_CHARS_PER_PAGE:
        return True, f"only {total_chars // units} chars per embedded image"
    return False, ""


def _pdf_page_images(data: bytes | None, path: str | None, pages: list[int]) -> list[dict]:
    import pymupdf

    if path:
        document = pymupdf.open(path)
    else:
        document = pymupdf.open(stream=_read_bytes(data, path), filetype="pdf")

    images = []
    try:
        for page_number in pages:
            if page_number < 1 or page_number > len(document):
                continue
            pixmap = document[page_number - 1].get_pixmap(dpi=RENDER_DPI)
            images.append(
                {
                    "label": f"p.{page_number}",
                    "mime_type": "image/png",
                    "data": pixmap.tobytes("png"),
                    "page": page_number,
                }
            )
    finally:
        document.close()
    return images


def _ooxml_images(data: bytes | None, path: str | None, limit: int) -> list[dict]:
    buffer = BytesIO(_read_bytes(data, path))
    images = []
    with zipfile.ZipFile(buffer) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.startswith(OOXML_MEDIA_DIRS) and name.lower().endswith(OOXML_IMAGE_EXTS)
        )
        for index, name in enumerate(names[:limit], start=1):
            extension = name.lower().rsplit(".", 1)[-1]
            mime = "image/jpeg" if extension in ("jpg", "jpeg") else f"image/{extension}"
            images.append(
                {
                    "label": f"image {index}",
                    "mime_type": mime,
                    "data": archive.read(name),
                    "page": None,
                }
            )
    return images


def extract_page_images(data: bytes | None, path: str | None, filename: str, meta: dict, blocks: list[SourceBlock]) -> list[dict]:
    limit = max_ocr_pages()
    lower = (filename or "").lower()

    if lower.endswith(".pdf"):
        pages = int(meta.get("pages") or 0)
        targets = underserved_pages(blocks, pages)
        if not targets:
            targets = list(range(1, pages + 1))
        return _pdf_page_images(data, path, targets[:limit])

    if lower.endswith((".docx", ".pptx", ".xlsx")):
        return _ooxml_images(data, path, limit)

    return []


def _ocr_one(image: dict, llm: LLMProvider, prompt: str = VISION_OCR_PROMPT) -> str:
    part = MediaPart(mime_type=image["mime_type"], data=image["data"])
    return llm.generate_text(prompt, parts=[part])


def _batch_prompt(base: str, count: int) -> str:
    return (
        f"{base}\n\n"
        f"You are given {count} images from a single document, in order.\n"
        f"Process EVERY image independently and return exactly {count} results.\n"
        'Each result has "index" (1-based, matching the image order) and "text".\n'
        "Never merge images together and never skip an image."
    )


def _batched_texts(
    items: list[dict],
    llm: LLMProvider,
    base_prompt: str,
    size: int,
    delay: float,
) -> list[str]:
    """Send images in batches — one request per `size` images.

    Free-tier Gemini allows only a handful of requests per minute, so batching
    is what makes vision OCR viable. Falls back to per-image calls if a batch
    response cannot be parsed.
    """
    texts: list[str] = ["" for _ in items]

    for start in range(0, len(items), size):
        batch = items[start : start + size]
        parts = [MediaPart(mime_type=item["mime_type"], data=item["data"]) for item in batch]
        parsed: dict[int, str] = {}
        batch_ok = False
        try:
            payload = llm.generate_json(_batch_prompt(base_prompt, len(batch)), json_schema=BATCH_SCHEMA, parts=parts)
            for entry in payload.get("results") or []:
                if isinstance(entry, dict) and entry.get("index") is not None:
                    parsed[int(entry["index"])] = str(entry.get("text") or "")
            batch_ok = True
        except Exception:
            batch_ok = False

        for offset, item in enumerate(batch):
            index = start + offset
            if parsed.get(offset + 1):
                texts[index] = parsed[offset + 1]
            elif batch_ok:
                try:
                    texts[index] = _ocr_one(item, llm, base_prompt)
                except Exception:
                    texts[index] = ""

        if delay and start + size < len(items):
            time.sleep(delay)

    return texts


def _to_blocks(items: list[dict], texts: list[str], name: str, kind: str) -> list[SourceBlock]:
    blocks: list[SourceBlock] = []
    for item, raw in zip(items, texts):
        for index, paragraph in enumerate(split_paragraphs(raw or ""), start=1):
            if "scanned by camscanner" in paragraph.lower():
                continue
            blocks.append(
                SourceBlock(
                    text=paragraph,
                    ref=f"{name} {item['label']} \u00b6{index}",
                    kind=kind,
                    page=item.get("page"),
                )
            )
    return blocks


def ocr_images(images: list[dict], llm: LLMProvider, name: str, workers: int = OCR_WORKERS) -> list[SourceBlock]:
    if not images:
        return []
    texts = _batched_texts(images, llm, VISION_OCR_PROMPT, batch_size(), batch_delay())
    return _to_blocks(images, texts, name, "ocr")


def ocr_figures(figures: list[dict], llm: LLMProvider, name: str, workers: int = OCR_WORKERS) -> list[SourceBlock]:
    if not figures:
        return []
    items = [
        {
            "label": f"p.{figure['page']} fig" if figure.get("page") else "figure",
            "mime_type": "image/png",
            "data": figure["data"],
            "page": figure.get("page"),
        }
        for figure in figures
    ]
    texts = _batched_texts(items, llm, FIGURE_PROMPT, batch_size(), batch_delay())
    blocks = _to_blocks(items, texts, name, "figure")
    captions = [figure.get("caption") for figure in figures]
    for block, caption in zip(blocks, captions):
        if caption and caption.lower() not in block.text.lower():
            block.text = f"{caption}\n{block.text}"
    return blocks


def _strip_junk(blocks: list[SourceBlock]) -> list[SourceBlock]:
    return [
        b
        for b in blocks
        if len((b.text or "").strip()) > 40 and "scanned by camscanner" not in (b.text or "").lower()
    ]


def ocr_fallback(
    data: bytes | None,
    path: str | None,
    filename: str,
    name: str,
    llm: LLMProvider,
    blocks: list[SourceBlock],
    meta: dict,
) -> tuple[list[SourceBlock], dict]:
    updates: dict = {}
    figures = meta.pop("figures", []) or []
    figure_blocks: list[SourceBlock] = []

    if figures:
        cap = max_figures()
        selected = figures[:cap]
        try:
            figure_blocks = ocr_figures(selected, llm, name)
            updates["figures"] = len(selected)
            if len(figures) > cap:
                updates["figures_skipped"] = len(figures) - cap
        except Exception as exc:
            updates["figure_error"] = f"{type(exc).__name__}: {exc}"

    page_blocks: list[SourceBlock] = []
    required, reason = needs_vision_ocr(blocks, meta, data, path, filename)
    if required:
        try:
            images = extract_page_images(data, path, filename, meta, blocks)
        except Exception as exc:
            updates["ocr_error"] = f"{type(exc).__name__}: {exc}"
            images = []
        if images:
            try:
                page_blocks = ocr_images(images, llm, name)
                updates["ocr_applied"] = True
                updates["ocr_reason"] = reason
                updates["ocr_pages"] = len(images)
            except Exception as exc:
                updates["ocr_error"] = f"{type(exc).__name__}: {exc}"
        else:
            updates.setdefault("ocr_applied", False)
            updates.setdefault("ocr_reason", reason)

    if not page_blocks and not figure_blocks:
        return blocks, updates

    base = _strip_junk(blocks) if page_blocks else list(blocks)
    merged = base + page_blocks + figure_blocks
    merged.sort(key=lambda b: (b.page is None, b.page or 0))
    updates["ocr_blocks"] = len(page_blocks) + len(figure_blocks)
    return merged, updates
