import os
import threading
from io import BytesIO

from engine.ingestion.chunking import split_paragraphs
from engine.ingestion.types import SourceBlock

SUPPORTED_EXTS = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".bmp",
    ".webp",
)

LABEL_KIND = {
    "title": "heading",
    "section_header": "heading",
    "text": "paragraph",
    "paragraph": "paragraph",
    "list_item": "paragraph",
    "code": "paragraph",
    "formula": "paragraph",
    "caption": "paragraph",
    "table": "table",
}

SKIP_LABELS = {"page_header", "page_footer", "picture", "reference", "footnote", "document_index"}

MIN_FIGURE_PIXELS = 20_000
MAX_FIGURE_CANDIDATES = 40
FIGURE_IMAGE_SCALE = 2.0


def _figure_payload(item, document, page: int | None, caption: str | None) -> dict | None:
    getter = getattr(item, "get_image", None)
    if getter is None:
        return None
    try:
        image = getter(document)
    except Exception:
        return None
    if image is None:
        return None
    width, height = getattr(image, "size", (0, 0))
    if width * height < MIN_FIGURE_PIXELS:
        return None
    buffer = BytesIO()
    try:
        image.convert("RGB").save(buffer, format="PNG")
    except Exception:
        return None
    return {
        "page": page,
        "caption": caption,
        "width": width,
        "height": height,
        "data": buffer.getvalue(),
    }

DEFAULT_MAX_DOCLING_PAGES = 120
_converter = None
_converter_lock = threading.Lock()


def max_docling_pages() -> int:
    try:
        return int(os.getenv("DOCLING_MAX_PAGES", DEFAULT_MAX_DOCLING_PAGES))
    except ValueError:
        return DEFAULT_MAX_DOCLING_PAGES


def docling_ocr_enabled() -> bool:
    return os.getenv("DOCLING_OCR", "0") == "1"


def _get_converter():
    global _converter
    with _converter_lock:
        if _converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            options = PdfPipelineOptions()
            options.do_ocr = docling_ocr_enabled()
            options.do_table_structure = True
            options.generate_picture_images = True
            options.images_scale = FIGURE_IMAGE_SCALE

            _converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )
    return _converter


def _open_pdf(data: bytes | None, path: str | None):
    import pymupdf

    if path:
        return pymupdf.open(path)
    return pymupdf.open(stream=_read_bytes(data, path), filetype="pdf")


def pdf_page_count(data: bytes | None, path: str | None) -> int:
    document = _open_pdf(data, path)
    try:
        return len(document)
    finally:
        document.close()


def _fast_pdf(data: bytes | None, path: str | None, name: str) -> tuple[list[SourceBlock], dict]:
    document = _open_pdf(data, path)
    blocks: list[SourceBlock] = []
    try:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            for index, paragraph in enumerate(split_paragraphs(text), start=1):
                blocks.append(
                    SourceBlock(
                        text=paragraph,
                        ref=f"{name} p.{page_number} \u00b6{index}",
                        kind="paragraph",
                        page=page_number,
                    )
                )
        meta = {"filename": name, "format": "pdf", "pages": len(document), "parser": "pymupdf-fast"}
    finally:
        document.close()
    return blocks, meta


def _read_bytes(data: bytes | None, path: str | None) -> bytes:
    if data is not None:
        return data
    if path:
        with open(path, "rb") as handle:
            return handle.read()
    raise ValueError("document ingestion needs 'data' or 'path'")


def _table_to_text(item) -> str:
    for method in ("export_to_markdown", "export_to_dataframe"):
        exporter = getattr(item, method, None)
        if exporter is None:
            continue
        try:
            rendered = exporter()
        except Exception:
            continue
        if isinstance(rendered, str) and rendered.strip():
            return rendered.strip()
        if hasattr(rendered, "to_markdown"):
            try:
                return rendered.to_markdown().strip()
            except Exception:
                continue
        if hasattr(rendered, "to_string"):
            return rendered.to_string().strip()
    return ""


def _convert(data: bytes | None, path: str | None, filename: str):
    converter = _get_converter()
    if path:
        source = path
    else:
        from docling.datamodel.base_models import DocumentStream

        source = DocumentStream(name=filename, stream=BytesIO(_read_bytes(data, path)))
    return converter.convert(source)


def parse_document(
    data: bytes | None, path: str | None, filename: str, name: str
) -> tuple[list[SourceBlock], dict]:
    lower = (filename or "").lower()
    if lower and not lower.endswith(SUPPORTED_EXTS):
        raise ValueError(
            f"unsupported document type: {filename!r} (supported: {', '.join(SUPPORTED_EXTS)})"
        )

    if lower.endswith(".pdf"):
        pages = pdf_page_count(data, path)
        if pages > max_docling_pages():
            return _fast_pdf(data, path, name)

    result = _convert(data, path, filename or "document")
    document = result.document

    blocks: list[SourceBlock] = []
    page_counters: dict[int, int] = {}
    current_heading: str | None = None
    table_count = 0
    figures: list[dict] = []
    pending_caption: str | None = None

    for item, level in document.iterate_items():
        label = str(getattr(item, "label", "") or "").lower()

        prov = getattr(item, "prov", None) or []
        page = prov[0].page_no if prov else None

        if label == "picture":
            if len(figures) < MAX_FIGURE_CANDIDATES:
                payload = _figure_payload(item, document, page, pending_caption)
                if payload is not None:
                    figures.append(payload)
            pending_caption = None
            continue

        if label == "caption":
            pending_caption = (getattr(item, "text", "") or "").strip() or None

        if label in SKIP_LABELS:
            continue

        kind = LABEL_KIND.get(label)
        if kind is None:
            continue

        if kind == "table":
            text = _table_to_text(item)
            if not text:
                continue
            table_count += 1
            ref = f"{name} table {table_count}"
        else:
            text = (getattr(item, "text", "") or "").strip()
            if not text:
                continue
            if page is not None:
                page_counters[page] = page_counters.get(page, 0) + 1
                ref = f"{name} p.{page} \u00b6{page_counters[page]}"
            else:
                page_counters[0] = page_counters.get(0, 0) + 1
                ref = f"{name} \u00a7{page_counters[0]}"

        if kind == "heading":
            current_heading = text

        blocks.append(
            SourceBlock(
                text=text,
                ref=ref,
                kind=kind,
                page=page,
                heading=current_heading,
            )
        )

    meta = {
        "filename": filename,
        "format": lower.rsplit(".", 1)[-1] if "." in lower else "unknown",
        "pages": len(document.pages),
        "tables": len(document.tables),
        "figures": figures,
        "parser": "docling",
    }
    return blocks, meta