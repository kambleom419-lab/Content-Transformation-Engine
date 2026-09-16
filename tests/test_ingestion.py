import base64
import io
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ingestion import infer_kind, infer_source_type, ingest, ingest_sources
from engine.ingestion.chunking import chunk_blocks, split_paragraphs
from engine.ingestion.documents import parse_document
from engine.ingestion.language import detect_language, normalize_to_english
from engine.ingestion.ocr import (
    chars_per_page,
    count_embedded_images,
    extract_page_images,
    missing_pages,
    needs_vision_ocr,
    ocr_fallback,
    ocr_figures,
    ocr_images,
    underserved_pages,
)
from engine.ingestion.types import SourceBlock
from engine.ingestion.web import extract_from_html
from engine.llm import LLMProvider
from engine.recipes import CONTENT_MODEL_SCHEMA, repair_content_model

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def make_png(color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeProvider(LLMProvider):
    """Records calls; returns deterministic text. No network."""

    name = "fake"

    def __init__(self):
        self.calls = []

    def generate_text(self, prompt, parts=None):
        self.calls.append({"prompt": prompt, "parts": parts or []})
        if "=== TEXT ===" in prompt:
            inner = prompt.split("=== TEXT ===", 1)[1].split("=== END TEXT ===")[0].strip()
            return "EN: " + inner
        if parts:
            return "Transcribed media line one.\n\nTranscribed media line two."
        return "plain output"

    def generate_json(self, prompt, json_schema=None):
        return {
            "title": "T",
            "severity": "CRITICAL",
            "source_type": "bogus",
            "facts": ["bare string fact", {"text": "real fact", "source_ref": "doc §1"}, {"no": "text"}],
            "iocs": "1.2.3.4",
            "key_messages": ["m1"],
        }


def make_pdf_bytes(lines: list[str], filename: str = "report.pdf") -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, 720, "Threat Advisory")
    pdf.setFont("Helvetica", 10)
    text = pdf.beginText(72, 700)
    for line in lines:
        text.textLine(line)
    pdf.drawText(text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_docx_bytes(paragraphs: list[str]) -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Threat Advisory", level=1)
    for para in paragraphs:
        document.add_paragraph(para)
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "CVE"
    table.rows[0].cells[1].text = "CVE-2026-4417"
    table.rows[1].cells[0].text = "IP"
    table.rows[1].cells[1].text = "203.0.113.5"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- chunking


def test_chunking_merges_and_preserves_refs():
    blocks = [
        SourceBlock(text="Short one.", ref="doc §1", source_id="doc"),
        SourceBlock(text="Short two.", ref="doc §2", source_id="doc"),
    ]
    out = chunk_blocks(blocks, max_chars=1000)
    assert len(out) == 1, out
    assert "doc §1" in out[0].ref and "doc §2" in out[0].ref, out[0].ref
    assert "Short one." in out[0].text and "Short two." in out[0].text


def test_chunking_splits_oversized_block():
    long_text = " ".join(f"Sentence number {i} about the incident." for i in range(80))
    out = chunk_blocks([SourceBlock(text=long_text, ref="doc p.1", source_id="doc")], max_chars=300, overlap_chars=50)
    assert len(out) > 1, "expected split"
    assert out[0].ref == "doc p.1"
    assert "(part 2)" in out[1].ref


def test_chunking_keeps_headings_separate():
    blocks = [
        SourceBlock(text="Section A", ref="doc §1", kind="heading", source_id="doc"),
        SourceBlock(text="Body text here.", ref="doc §2", source_id="doc"),
    ]
    out = chunk_blocks(blocks, max_chars=1000)
    assert out[0].kind == "heading" and out[0].text == "Section A"
    assert len(out) == 2


def test_chunking_preserves_source_id():
    blocks = [
        SourceBlock(text="Alpha text.", ref="a §1", source_id="a"),
        SourceBlock(text="Beta text.", ref="b §1", source_id="b"),
    ]
    out = chunk_blocks(blocks, max_chars=1000)
    assert out[0].source_id == "a"


def test_split_paragraphs():
    assert split_paragraphs("A\n\nB\n\n\nC") == ["A", "B", "C"]


# ---------------------------------------------------------------- text ingest


def test_text_ingest_offline():
    src = {"id": "alert-1", "kind": "text", "text": "First paragraph.\n\nSecond paragraph."}
    result = ingest(src, FakeProvider())
    assert result.kind == "text"
    assert result.source_id == "alert-1"
    assert result.blocks
    assert all(b.ref and b.text for b in result.blocks)
    first = result.corpus()[0]
    assert first["source_ref"].startswith("alert-1")
    assert first["source_id"] == "alert-1"


# ---------------------------------------------------------------- documents (docling)


def test_docling_pdf_bytes():
    lines = [
        "A critical remote code execution vulnerability affects SecureMail Gateway 3.2.",
        "Tracked as CVE-2026-4417, it allows unauthenticated command execution.",
        "The vendor released patched version 3.2.1 and urges immediate upgrade.",
    ]
    blocks, meta = parse_document(make_pdf_bytes(lines), None, "report.pdf", "report.pdf")
    assert meta["parser"] == "docling"
    assert meta["pages"] >= 1
    joined = " ".join(b.text for b in blocks)
    assert "SecureMail" in joined
    assert "CVE-2026-4417" in joined
    assert all(b.ref.startswith("report.pdf") for b in blocks)


def test_docling_docx_bytes():
    blocks, meta = parse_document(
        make_docx_bytes(["Critical RCE in SecureMail Gateway 3.2.", "Patch immediately."]),
        None,
        "advisory.docx",
        "advisory.docx",
    )
    assert meta["format"] == "docx"
    joined = " ".join(b.text for b in blocks)
    assert "SecureMail" in joined
    kinds = {b.kind for b in blocks}
    assert "heading" in kinds, kinds


def test_docling_unsupported_extension():
    try:
        parse_document(b"x", None, "archive.zip", "archive.zip")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "unsupported" in str(exc).lower()


# ---------------------------------------------------------------- web


def test_web_extract_from_html_fallback():
    html = """
    <html><head><title>Advisory Page</title></head>
    <body>
      <nav>menu junk</nav>
      <article>
        <h1>Critical RCE</h1>
        <p>An unauthenticated attacker can execute commands.</p>
        <script>var x = 1;</script>
      </article>
    </body></html>
    """
    blocks, title = extract_from_html(html, "https://example.org/a")
    assert title == "Advisory Page"
    texts = " ".join(b.text for b in blocks)
    assert "menu junk" not in texts
    assert "var x" not in texts
    assert "execute commands" in texts
    assert blocks[0].kind == "heading"


def test_web_extract_with_docling_primary():
    from engine.ingestion.web import _extract_with_docling

    html = """
    <html><head><title>Advisory</title></head>
    <body>
      <nav>theme chrome</nav>
      <article>
        <h1>Critical RCE</h1>
        <p>A critical remote code execution flaw affects SecureMail Gateway 3.2.</p>
        <p>Patch to version 3.2.1 immediately.</p>
      </article>
    </body></html>
    """
    blocks, title = _extract_with_docling(html, "https://example.org/a")
    joined = " ".join(b.text for b in blocks)
    assert blocks, "docling html path produced nothing"
    assert "SecureMail" in joined
    assert "theme chrome" not in joined
    assert title


# ---------------------------------------------------------------- language


def test_language_detection_and_normalization():
    spanish = "Esta es una advertencia de seguridad crítica sobre el producto SecureMail."
    assert isinstance(detect_language(spanish), str)

    blocks = [SourceBlock(text=spanish, ref="doc §1")]
    provider = FakeProvider()
    out, translated = normalize_to_english(blocks, provider, "es", [])
    assert translated is True
    assert out[0].text.startswith("EN: ")
    assert out[0].ref == "doc §1"


def test_language_skips_english():
    blocks = [SourceBlock(text="Already English.", ref="doc §1")]
    provider = FakeProvider()
    out, translated = normalize_to_english(blocks, provider, "en", [])
    assert translated is False
    assert provider.calls == []


# ---------------------------------------------------------------- image / media


def test_image_ingest_uses_vision():
    provider = FakeProvider()
    result = ingest(
        {"id": "shot", "kind": "image", "data": b"\x89PNG", "mime_type": "image/png"},
        provider,
    )
    assert result.meta.get("ocr") is True
    assert result.blocks
    assert provider.calls and provider.calls[0]["parts"]


def test_media_requires_path():
    try:
        ingest({"id": "clip", "kind": "media"}, FakeProvider())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "path" in str(exc)


# ---------------------------------------------------------------- dispatch


def test_infer_kind_and_source_type():
    assert infer_kind({"text": "hi"}) == "text"
    assert infer_kind({"url": "https://x"}) == "url"
    assert infer_kind({"filename": "a.PDF"}) == "document"
    assert infer_kind({"filename": "a.pptx"}) == "document"
    assert infer_kind({"filename": "a.jpg"}) == "image"
    assert infer_kind({"filename": "a.mp4"}) == "media"
    assert infer_source_type({"filename": "critical_advisory.pdf"}, "document") == "advisory"
    assert infer_source_type({}, "text") == "report"


# ---------------------------------------------------------------- multi-source


def test_multi_source_ingest():
    sources = [
        {"id": "doc-a", "kind": "text", "text": "Advisory A paragraph one.\n\nAdvisory A paragraph two."},
        {"id": "doc-b", "kind": "text", "text": "Report B paragraph one.\n\nReport B paragraph two."},
    ]
    corpus, descriptors, warnings = ingest_sources(sources, FakeProvider())
    assert len(descriptors) == 2
    ids = {d["source_id"] for d in descriptors}
    assert ids == {"doc-a", "doc-b"}
    source_ids = {c["source_id"] for c in corpus}
    assert source_ids == {"doc-a", "doc-b"}
    refs = [c["source_ref"] for c in corpus]
    assert any(r.startswith("doc-a") for r in refs)
    assert any(r.startswith("doc-b") for r in refs)


def test_multi_source_dedupes_duplicate_ids():
    sources = [
        {"id": "same", "kind": "text", "text": "First copy text here."},
        {"id": "same", "kind": "text", "text": "Second copy text here."},
    ]
    _corpus, descriptors, _warnings = ingest_sources(sources, FakeProvider())
    ids = [d["source_id"] for d in descriptors]
    assert len(set(ids)) == 2, ids


def test_multi_source_skips_failing_source():
    sources = [
        {"id": "good", "kind": "text", "text": "Valid content for ingestion."},
        {"id": "bad", "kind": "media"},
    ]
    corpus, descriptors, warnings = ingest_sources(sources, FakeProvider())
    assert [d["source_id"] for d in descriptors] == ["good"]
    assert warnings and "bad" in warnings[0]
    assert corpus


def test_multi_source_all_fail_raises():
    try:
        ingest_sources([{"id": "bad", "kind": "media"}], FakeProvider())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "no source content" in str(exc)


# ---------------------------------------------------------------- ocr fallback


class FakeOcrProvider(LLMProvider):
    name = "fake-ocr"

    def __init__(self, text="Handwritten note line one.\n\nScanned by CamScanner", batch_text=None):
        self.text = text
        self.batch_text = batch_text if batch_text is not None else text
        self.calls = 0
        self.batch_calls = 0
        self.batch_sizes: list[int] = []

    def generate_text(self, prompt, parts=None):
        self.calls += 1
        assert parts, "ocr must send a media part"
        return self.text

    def generate_json(self, prompt, json_schema=None, parts=None):
        self.batch_calls += 1
        if parts:
            self.batch_sizes.append(len(parts))
            return {"results": [{"index": i + 1, "text": self.batch_text} for i in range(len(parts))]}
        return {}


class PartialBatchProvider(FakeOcrProvider):
    """Batch succeeds but omits the second entry, forcing a per-image retry."""

    def generate_json(self, prompt, json_schema=None, parts=None):
        self.batch_calls += 1
        self.batch_sizes.append(len(parts or []))
        return {"results": [{"index": 1, "text": self.batch_text}]}


def with_batch(size: int, delay: float = 0.0):
    os.environ["OCR_BATCH_SIZE"] = str(size)
    os.environ["OCR_BATCH_DELAY_S"] = str(delay)
    return size


def test_ocr_thin_detection_pages():
    blocks = [
        SourceBlock(text="Short.", ref="d p.9 ¶1", page=9),
        SourceBlock(text="Short.", ref="d p.20 ¶1", page=20),
    ]
    meta = {"pages": 20}
    required, reason = needs_vision_ocr(blocks, meta, b"x", None, "d.pdf")
    assert required is True
    assert "0/20" in reason or "/20 pages" in reason


def test_ocr_not_needed_when_text_is_dense():
    blocks = [
        SourceBlock(text="A" * 400, ref=f"d p.{page} ¶1", page=page)
        for page in range(1, 7)
    ]
    meta = {"pages": 6}
    required, reason = needs_vision_ocr(blocks, meta, b"x", None, "d.pdf")
    assert required is False, reason


def test_ocr_thin_detection_for_ooxml_images():
    document = __import__("docx").Document()
    document.add_paragraph("Scanned by CamScanner")
    document.add_picture(io.BytesIO(make_png((255, 0, 0))))
    document.add_picture(io.BytesIO(make_png((0, 0, 255))))
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()

    assert count_embedded_images(data, None, "notes.docx") == 2
    blocks = [SourceBlock(text="Scanned by CamScanner", ref="notes.docx §1")]
    required, reason = needs_vision_ocr(blocks, {"pages": 0}, data, None, "notes.docx")
    assert required is True
    assert "embedded image" in reason


def test_ocr_missing_pages():
    blocks = [SourceBlock(text="x", ref="d p.1 ¶1", page=1), SourceBlock(text="y", ref="d p.3 ¶1", page=3)]
    assert missing_pages(blocks, 4) == [2, 4]


def test_underserved_pages_includes_watermark_only_pages():
    """Regression: junk-text pages must be OCR'd, not treated as covered."""
    blocks = [
        SourceBlock(text="Scanned by CamScanner", ref="d p.1 ¶1", page=1),
        SourceBlock(text="Scanned by CamScanner", ref="d p.2 ¶1", page=2),
        SourceBlock(text="Real content. " * 40, ref="d p.3 ¶1", page=3),
    ]
    assert chars_per_page(blocks)[3] > 250
    assert underserved_pages(blocks, 3) == [1, 2]


def test_ocr_images_skips_watermark_and_builds_refs():
    with_batch(4)
    provider = FakeOcrProvider()
    images = [
        {"label": "p.1", "mime_type": "image/png", "data": TINY_PNG, "page": 1},
        {"label": "p.2", "mime_type": "image/png", "data": TINY_PNG, "page": 2},
    ]
    blocks = ocr_images(images, provider, "notes.pdf")
    texts = [b.text for b in blocks]
    assert all("camscanner" not in t.lower() for t in texts), texts
    assert any("Handwritten note" in t for t in texts)
    assert blocks[0].kind == "ocr"
    assert blocks[0].ref.startswith("notes.pdf p.1")


def test_ocr_batches_multiple_images_into_one_request():
    with_batch(4)
    provider = FakeOcrProvider(batch_text="Recovered text.")
    images = [
        {"label": f"p.{i}", "mime_type": "image/png", "data": TINY_PNG, "page": i}
        for i in range(1, 6)
    ]
    blocks = ocr_images(images, provider, "doc.pdf")
    assert provider.batch_calls == 2, provider.batch_calls
    assert provider.calls == 0, "should not fall back to per-image calls"
    assert provider.batch_sizes == [4, 1], provider.batch_sizes
    assert len([b for b in blocks if "Recovered" in b.text]) == 5


def test_ocr_batch_falls_back_when_entry_missing():
    with_batch(4)
    provider = PartialBatchProvider(batch_text="From batch.")
    images = [
        {"label": f"p.{i}", "mime_type": "image/png", "data": TINY_PNG, "page": i}
        for i in range(1, 3)
    ]
    blocks = ocr_images(images, provider, "doc.pdf")
    assert provider.batch_calls == 1
    assert provider.calls == 1, "missing entry should be retried per image"
    assert len([b for b in blocks if b.text]) == 2


def test_ocr_single_image_needs_one_call():
    with_batch(4)
    provider = FakeOcrProvider(batch_text="Only one.")
    images = [{"label": "p.1", "mime_type": "image/png", "data": TINY_PNG, "page": 1}]
    blocks = ocr_images(images, provider, "doc.pdf")
    assert provider.batch_calls == 1
    assert provider.batch_sizes == [1]
    assert blocks and "Only one." in blocks[0].text


def test_ocr_figures_uses_batch_and_prefixes_caption():
    with_batch(4)
    provider = FakeOcrProvider(batch_text="CHART DESCRIPTION: rising trend.")
    figures = [
        {"page": 2, "caption": "Figure 2: observed indicators", "data": TINY_PNG},
        {"page": 3, "caption": None, "data": TINY_PNG},
    ]
    blocks = ocr_figures(figures, provider, "report.pdf")
    assert provider.batch_calls == 1
    assert len(blocks) == 2
    assert blocks[0].kind == "figure"
    assert "observed indicators" in blocks[0].text
    assert blocks[0].ref.startswith("report.pdf p.2 fig")


def test_ocr_extract_ooxml_images():
    document = __import__("docx").Document()
    document.add_picture(io.BytesIO(TINY_PNG))
    buffer = io.BytesIO()
    document.save(buffer)
    images = extract_page_images(buffer.getvalue(), None, "notes.docx", {"pages": 0}, [])
    assert len(images) == 1
    assert images[0]["mime_type"] == "image/png"


def test_ocr_fallback_replaces_thin_blocks():
    provider = FakeOcrProvider(text="Real handwritten content recovered.")
    blocks = [SourceBlock(text="Scanned by CamScanner", ref="notes.docx §1")]
    merged, info = ocr_fallback(
        b"not-a-real-zip", None, "notes.docx", "notes.docx", provider, blocks, {"pages": 0}
    )
    assert info.get("ocr_error"), info


def test_ocr_fallback_skips_when_not_thin():
    provider = FakeOcrProvider()
    blocks = [SourceBlock(text="B" * 500, ref=f"d p.{p} ¶1", page=p) for p in range(1, 4)]
    merged, info = ocr_fallback(b"x", None, "d.pdf", "d.pdf", provider, blocks, {"pages": 3})
    assert info == {}
    assert merged == blocks
    assert provider.calls == 0 and provider.batch_calls == 0


# ---------------------------------------------------------------- repair / graph


def test_repair_content_model():
    raw = {
        "severity": "CRITICAL",
        "source_type": "bogus",
        "facts": ["bare", {"text": "ok", "source_ref": "d §1"}, {"junk": 1}],
        "iocs": "1.2.3.4",
        "key_messages": None,
    }
    fixed = repair_content_model(raw, fallback_source_type="advisory", fallback_language="hi")
    assert fixed["severity"] == "critical"
    assert fixed["source_type"] == "advisory"
    assert fixed["language"] == "hi"
    assert fixed["iocs"] == ["1.2.3.4"]
    assert fixed["key_messages"] == []
    assert fixed["facts"] == [
        {"text": "bare", "source_ref": ""},
        {"text": "ok", "source_ref": "d §1"},
    ]
    assert CONTENT_MODEL_SCHEMA["properties"]["severity"]["enum"] == ["info", "low", "medium", "high", "critical"]


def test_graph_ingest_single_source():
    from engine.graph import ingest_source
    from engine.state import empty_state

    state = empty_state({"id": "g-1", "kind": "text", "text": "Para one.\n\nPara two."}, ["advisory"])
    out = ingest_source(state, FakeProvider())
    assert out["source_input"]["source_language"]
    assert out["source_input"]["source_type"] == "report"
    assert len(out["sources"]) == 1
    assert out["corpus"]


def test_graph_ingest_multi_source():
    from engine.graph import ingest_source
    from engine.state import empty_state

    state = empty_state(
        {"tone": "formal"},
        ["advisory"],
        sources=[
            {"id": "a", "kind": "text", "text": "Source A content paragraph."},
            {"id": "b", "kind": "text", "text": "Source B content paragraph."},
        ],
    )
    out = ingest_source(state, FakeProvider())
    assert out["source_input"]["kind"] == "multi"
    assert len(out["sources"]) == 2
    assert len({c["source_id"] for c in out["corpus"]}) == 2


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
