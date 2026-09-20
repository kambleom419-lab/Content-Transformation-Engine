"""
Deterministic renderers: artefact draft (dict) -> real file bytes.

The model produces blueprints; these functions produce the deliverable. Nothing
here calls a model, so a given draft always renders byte-identically — which is
what makes the sha256 hashes in the export manifest meaningful.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from engine.config import get_artefacts_dir
from engine.recipes import ARTEFACT_PROFILES

FIELD_LABELS = {
    "severity": "Severity",
    "executive_summary": "Executive Summary",
    "affected_systems": "Affected Systems",
    "details": "Details",
    "iocs": "Indicators of Compromise",
    "mitigations": "Mitigations",
    "references": "References",
    "title": "Title",
    "summary": "Summary",
    "key_points": "Key Points",
    "recommendations": "Recommendations",
    "headline": "Headline",
    "body": "Body",
    "cta": "Call to Action",
    "hashtags": "Hashtags",
    "tweets": "Thread",
    "script": "Script",
    "storyboard": "Storyboard",
    "scene_descriptions": "Scene Descriptions",
    "narration": "Narration",
    "subtitles": "Subtitles",
    "visual_recommendations": "Visual Recommendations",
    "content": "Content",
    "layout_recommendations": "Layout Recommendations",
    "key_messaging": "Key Messaging",
}


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                text = " — ".join(str(v) for v in item.values() if v)
                if text.strip():
                    out.append(text.strip())
        return out
    return [str(value)]


def _title_for(artefact_type: str, draft: dict, content_model: dict | None = None) -> str:
    model = content_model or {}
    for candidate in (draft.get("title"), draft.get("headline"), model.get("title")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ARTEFACT_PROFILES[artefact_type]["label"]


def render_markdown(artefact_type: str, draft: dict, content_model: dict | None = None) -> str:
    profile = ARTEFACT_PROFILES[artefact_type]
    lines = [f"# {_title_for(artefact_type, draft, content_model)}", ""]
    for field in profile["fields"]:
        items = _as_list(draft.get(field))
        if not items:
            continue
        lines.append(f"## {_label(field)}")
        lines.append("")
        if len(items) == 1:
            lines.append(items[0])
        else:
            lines.extend(f"- {item}" for item in items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_linkedin_post(draft: dict, *_) -> str:
    """
    A publishable post: hook, body, call to action, hashtags.

    The generic field-walk produced a spec sheet ("HEADLINE", "BODY", ...) which
    is not something an operator can paste into LinkedIn.
    """
    blocks: list[str] = []
    for field in ("headline", "body", "cta"):
        items = _as_list(draft.get(field))
        if items:
            blocks.append("\n\n".join(items))

    hashtags = _as_list(draft.get("hashtags"))
    if hashtags:
        blocks.append(" ".join(tag if tag.startswith("#") else f"#{tag}" for tag in hashtags))

    return "\n\n".join(blocks).rstrip() + "\n"


def render_plaintext(artefact_type: str, draft: dict, content_model: dict | None = None) -> str:
    if artefact_type == "linkedin_post":
        return render_linkedin_post(draft)

    if artefact_type == "x_thread":
        tweets = _as_list(draft.get("tweets"))
        if not tweets:
            return ""

        total = len(tweets)
        # Models often number their own tweets ("1/ ..."). Don't number twice.
        if any(re.match(r"^\s*\d+\s*[/.)]", tweet) for tweet in tweets):
            body = "\n\n".join(tweets)
        else:
            body = "\n\n".join(f"{i}/{total}\n{tweet}" for i, tweet in enumerate(tweets, 1))

        # Posts stay clean above the divider for copy-paste; the checks go below.
        longest = max(len(tweet) for tweet in tweets)
        over = [index for index, tweet in enumerate(tweets, 1) if len(tweet) > 280]
        summary = [f"{total} posts  ·  longest {longest}/280 characters"]
        if over:
            summary.append(f"OVER THE 280 LIMIT: post {', '.join(str(i) for i in over)}")

        return f"{body}\n\n---\n" + "\n".join(summary) + "\n"

    profile = ARTEFACT_PROFILES[artefact_type]
    blocks: list[str] = []
    for field in profile["fields"]:
        items = _as_list(draft.get(field))
        if not items:
            continue
        blocks.append(_label(field).upper())
        blocks.extend(items)
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def render_json(draft: dict, *_) -> str:
    return json.dumps(draft, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Infographic poster — a real PNG, not a text brief
# ---------------------------------------------------------------------------
#
# An infographic is inherently visual, so the deliverable is an image. Pillow is
# used rather than HTML + a headless browser because this is a *runtime* render:
# making the engine depend on a bundled browser would be a heavy, odd dependency
# for an on-prem deployment.

POSTER_SIZE = (1200, 1600)
POSTER_MARGIN = 88

POSTER_COLOURS = {
    "ink": "#0F172A",
    "body": "#334155",
    "muted": "#64748B",
    "faint": "#94A3B8",
    "rule": "#E2E8F0",
    "accent": "#1D4ED8",
    "accent_soft": "#EFF4FF",
    "page": "#FFFFFF",
}

SEVERITY_COLOURS = {
    "critical": "#B91C1C",
    "high": "#C2410C",
    "medium": "#B45309",
    "low": "#1D4ED8",
    "info": "#475569",
}

# Font discovery: Windows, Linux and macOS paths, then Pillow's built-in fallback.
POSTER_FONTS = [
    (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\segoeui.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial.ttf"),
]


def _poster_font_paths() -> tuple[str | None, str | None]:
    for bold, regular in POSTER_FONTS:
        if Path(bold).is_file() and Path(regular).is_file():
            return bold, regular
    return None, None


def _poster_font(size: int, bold: bool = False):
    from PIL import ImageFont

    bold_path, regular_path = _poster_font_paths()
    chosen = bold_path if bold else regular_path
    if chosen:
        try:
            return ImageFont.truetype(chosen, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in str(text or "").split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_infographic_png(
    draft: dict,
    content_model: dict | None = None,
    artefact_type: str = "infographic",
    options: dict | None = None,
) -> bytes:
    from PIL import Image, ImageDraw

    palette = PPTX_TEMPLATES[resolve_pptx_template(options)]

    def rgb(key: str) -> str:
        return "#{:02X}{:02X}{:02X}".format(*palette[key])

    model = content_model or {}
    title = _title_for(artefact_type, draft, content_model)
    severity = str(model.get("severity") or "").strip().lower()

    page_bg = rgb("slide_bg")
    ink = rgb("ink")
    body_col = rgb("body")
    muted = rgb("muted")
    rule = rgb("rule")
    accent = rgb("accent")
    chip_bg = rgb("chip_bg")
    chip_text = rgb("chip_text")
    # Severity stays semantic — it carries meaning — while the template accent
    # styles everything else.
    band = SEVERITY_COLOURS.get(severity, accent)

    width, height = POSTER_SIZE
    margin = POSTER_MARGIN
    inner = width - margin * 2

    image = Image.new("RGB", POSTER_SIZE, page_bg)
    draw = ImageDraw.Draw(image)

    f_badge = _poster_font(26, bold=True)
    f_title = _poster_font(62, bold=True)
    f_section = _poster_font(24, bold=True)
    f_body = _poster_font(28)
    f_small = _poster_font(22)
    f_micro = _poster_font(20)

    # Header treatment differs STRUCTURALLY between templates, not just by colour:
    # "bold" fills a solid block and sets the title in white. Without that, a
    # critical advisory makes every template look the same, because the red
    # severity colour masks whatever accent the template chose.
    header_block = bool(palette.get("poster_header_block"))
    if header_block:
        block_bottom = margin + 250
        draw.rectangle([0, 0, width, block_bottom], fill=accent)
    else:
        draw.rectangle([0, 0, width, 14], fill=band)

    y = margin + 20

    # badge
    badge_text = (severity or "advisory").upper()
    badge_w = draw.textlength(badge_text, font=f_badge) + 40
    badge_bg = "#FFFFFF" if header_block else band
    badge_fg = accent if header_block else "#FFFFFF"
    draw.rounded_rectangle([margin, y, margin + badge_w, y + 46], radius=23, fill=badge_bg)
    draw.text((margin + 20, y + 9), badge_text, font=f_badge, fill=badge_fg)
    y += 82

    # title
    title_colour = "#FFFFFF" if header_block else ink
    for line in _wrap(draw, title, f_title, inner):
        draw.text((margin, y), line, font=f_title, fill=title_colour)
        y += 74

    if header_block:
        y = max(block_bottom, y) + 44
    else:
        y += 18
        draw.line([margin, y, width - margin, y], fill=rule, width=2)
        y += 44

    def section(label: str) -> None:
        nonlocal y
        draw.text((margin, y), label.upper(), font=f_section, fill=accent)
        y += 44

    def bullets(items: list[str], bullet: str = "\u25b8") -> None:
        nonlocal y
        for item in items:
            lines = _wrap(draw, item, f_body, inner - 40)
            draw.text((margin, y), bullet, font=f_body, fill=accent)
            for line in lines:
                draw.text((margin + 34, y), line, font=f_body, fill=body_col)
                y += 40
            y += 10

    # The infographic profile names this field "key_messaging"; the content model
    # calls it "key_messages". Accept either, and fall back to the content model so
    # the poster is never empty when the draft omitted it.
    key_messages = (
        _as_list(draft.get("key_messaging"))
        or _as_list(draft.get("key_messages"))
        or _as_list(model.get("key_messages"))
    )
    if key_messages:
        section("Key messages")
        bullets(key_messages[:5])
        y += 22

    content = _as_list(draft.get("content"))
    if content:
        section("Detail")
        for block in content[:4]:
            for line in _wrap(draw, block, f_body, inner):
                draw.text((margin, y), line, font=f_body, fill=body_col)
                y += 40
            y += 14
        y += 10

    iocs = _as_list(model.get("iocs"))
    if iocs and y < height - 300:
        section("Indicators")
        x = margin
        row_height = 48
        for ioc in iocs[:8]:
            chip_w = draw.textlength(ioc, font=f_micro) + 30
            if x + chip_w > width - margin:
                x = margin
                y += row_height
            draw.rounded_rectangle([x, y, x + chip_w, y + 36], radius=8, fill=chip_bg)
            draw.text((x + 15, y + 8), ioc, font=f_micro, fill=chip_text)
            x += chip_w + 12
        y += row_height + 20

    # footer provenance
    footer_y = height - margin - 56
    draw.line([margin, footer_y, width - margin, footer_y], fill=rule, width=2)
    source_label = model.get("source_type") or "source document"
    draw.text((margin, footer_y + 18),
              f"Generated by the Content Transformation Engine  ·  {source_label}",
              font=f_small, fill=muted)
    if model.get("title"):
        stamp = "human-reviewed"
        stamp_w = draw.textlength(stamp, font=f_micro) + 28
        draw.rounded_rectangle([width - margin - stamp_w, footer_y + 12,
                                width - margin, footer_y + 48], radius=18, outline=rule, width=2)
        draw.text((width - margin - stamp_w + 14, footer_y + 20), stamp, font=f_micro, fill=muted)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Template previews
# ---------------------------------------------------------------------------
#
# Rendered with sample content so an operator can see what a template looks like
# before committing a run to it.

TEMPLATE_SAMPLE_DRAFT = {
    "content": (
        "A critical remote code execution vulnerability affects SecureMail Gateway 3.2. "
        "An unauthenticated attacker can execute commands on the host, and government "
        "email infrastructure connected to the public internet is exposed."
    ),
    "key_messaging": [
        "Unauthenticated remote code execution",
        "Government email infrastructure is affected",
        "Patched version 3.2.1 is available now",
    ],
    "layout_recommendations": ["Severity banner across the top", "Indicators as a chip row"],
}

TEMPLATE_SAMPLE_MODEL = {
    "title": "SecureMail Gateway RCE",
    "severity": "critical",
    "source_type": "advisory",
    "iocs": ["CVE-2026-4417", "198.51.100.23"],
}


def render_template_preview(template_key: str) -> bytes:
    """Render an infographic using sample content, so a template can be previewed."""
    return render_infographic_png(
        TEMPLATE_SAMPLE_DRAFT,
        TEMPLATE_SAMPLE_MODEL,
        "infographic",
        {"template": template_key},
    )


# ---------------------------------------------------------------------------
# Presentation templates
# ---------------------------------------------------------------------------
#
# A template is a palette plus one structural flag, so adding a new look is a
# data change rather than new layout code.

PPTX_TEMPLATES = {
    "classic": {
        "label": "Classic",
        "blurb": "Dark cover, clean white slides, blue accent",
        "cover_bg": (0x0F, 0x17, 0x2A),
        "slide_bg": (0xFF, 0xFF, 0xFF),
        "ink": (0x0F, 0x17, 0x2A),
        "body": (0x33, 0x41, 0x55),
        "muted": (0x7A, 0x86, 0x99),
        "accent": (0x1D, 0x4E, 0xD8),
        "rule": (0xE2, 0xE8, 0xF0),
        "note_bg": (0xF4, 0xF7, 0xFB),
        "cover_accent": (0x1D, 0x4E, 0xD8),
        "cover_sub": (0x9A, 0xA6, 0xB8),
        "pill_fill": (0x1D, 0x4E, 0xD8),
        "pill_text": (0xFF, 0xFF, 0xFF),
        "chip_bg": (0xEF, 0xF4, 0xFF),
        "chip_text": (0x1D, 0x4E, 0xD8),
        "top_bar": False,
    },
    "midnight": {
        "label": "Midnight",
        "blurb": "Dark throughout — technical, operations-room feel",
        "cover_bg": (0x07, 0x0A, 0x12),
        "slide_bg": (0x11, 0x18, 0x27),
        "ink": (0xF5, 0xF7, 0xFA),
        "body": (0xC3, 0xCC, 0xD9),
        "muted": (0x8A, 0x94, 0xA6),
        "accent": (0xF5, 0x9E, 0x0B),
        "rule": (0x2A, 0x35, 0x45),
        "note_bg": (0x1B, 0x23, 0x30),
        "cover_accent": (0xF5, 0x9E, 0x0B),
        "cover_sub": (0x8A, 0x94, 0xA6),
        "pill_fill": (0xF5, 0x9E, 0x0B),
        "pill_text": (0x0B, 0x12, 0x20),
        "chip_bg": (0x1B, 0x23, 0x30),
        "chip_text": (0xF5, 0x9E, 0x0B),
        "top_bar": False,
    },
    "bold": {
        "label": "Bold",
        "blurb": "High contrast, heavy header band, large type",
        "cover_bg": (0x1D, 0x4E, 0xD8),
        "slide_bg": (0xFF, 0xFF, 0xFF),
        "ink": (0x0B, 0x12, 0x20),
        "body": (0x33, 0x41, 0x55),
        "muted": (0x64, 0x74, 0x8B),
        "accent": (0xDC, 0x26, 0x26),
        "rule": (0xE2, 0xE8, 0xF0),
        "note_bg": (0xF1, 0xF5, 0xF9),
        "cover_accent": (0xFF, 0xFF, 0xFF),
        "cover_sub": (0xD9, 0xE6, 0xFF),
        "pill_fill": (0xFF, 0xFF, 0xFF),
        "pill_text": (0x1D, 0x4E, 0xD8),
        "chip_bg": (0xFD, 0xEC, 0xEC),
        "chip_text": (0xDC, 0x26, 0x26),
        "top_bar": True,
        "poster_header_block": True,
    },
}

DEFAULT_PPTX_TEMPLATE = "classic"

# Structural variant per template, kept separate from the palette on purpose:
# a palette changes how a deck *looks*, a layout changes what it *is*. "Classic"
# and "Bold" are both light decks, so without a layout difference they would be
# near-identical — the palette alone is not enough to tell them apart.
PPTX_LAYOUTS = {
    "classic": "plain",      # eyebrow, title, thin accent rule, bullets
    "midnight": "sidebar",   # full-height accent spine down the left edge
    "bold": "banded",        # colour band behind the title + corner shard
}


def resolve_pptx_template(options: dict | None) -> str:
    """Pick a template from run options, falling back rather than raising."""
    chosen = str((options or {}).get("template") or "").strip().lower()
    return chosen if chosen in PPTX_TEMPLATES else DEFAULT_PPTX_TEMPLATE


def render_pptx(
    draft: dict,
    content_model: dict | None = None,
    artefact_type: str = "presentation",
    options: dict | None = None,
) -> bytes:
    """
    A designed deck, in one of several templates.

    The earlier version used PowerPoint's built-in layouts, which is why it
    looked like a default template. This builds slides from blank layouts and
    places every element, so the deck carries our own typography, spacing and
    accent colour instead of inheriting whatever theme the viewer has.
    """
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt

    palette = PPTX_TEMPLATES[resolve_pptx_template(options)]

    def rgb(key):
        return RGBColor(*palette[key])

    INK = rgb("ink")
    BODY = rgb("body")
    MUTED = rgb("muted")
    ACCENT = rgb("accent")
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    SLIDE_BG = rgb("slide_bg")
    RULE = rgb("rule")
    FONT = "Segoe UI"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    width = prs.slide_width
    height = prs.slide_height

    def rect(slide, left, top, w, h, fill):
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def text(slide, left, top, w, h, value, size, color, bold=False, align=PP_ALIGN.LEFT, spacing=1.15):
        box = slide.shapes.add_textbox(left, top, w, h)
        frame = box.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = MSO_ANCHOR.TOP
        para = frame.paragraphs[0]
        para.text = value
        para.alignment = align
        para.line_spacing = spacing
        run = para.runs[0]
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = FONT
        return box

    def bullets(slide, left, top, w, h, items, size=18, color=None, gap=10):
        box = slide.shapes.add_textbox(left, top, w, h)
        frame = box.text_frame
        frame.word_wrap = True
        for index, item in enumerate(items[:6]):
            para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            para.text = item if index == 0 else f"\u2022  {item}"
            if index == 0:
                para.text = f"\u2022  {item}"
            para.line_spacing = 1.3
            para.space_after = Pt(gap)
            run = para.runs[0]
            run.font.size = Pt(size)
            run.font.color.rgb = color or BODY
            run.font.name = FONT
        return box

    def footer(slide, number: int) -> None:
        rect(slide, Inches(0.9), height - Inches(0.86), width - Inches(1.8), Pt(1), RULE)
        text(slide, Inches(0.9), height - Inches(0.72), Inches(9), Inches(0.3),
             "Content Transformation Engine", 9, MUTED)
        text(slide, width - Inches(1.7), height - Inches(0.72), Inches(0.8), Inches(0.3),
             str(number), 9, MUTED, align=PP_ALIGN.RIGHT)

    # ---------------------------------------------------------------- cover
    title = _title_for(artefact_type, draft, content_model)
    cover = prs.slides.add_slide(blank)
    rect(cover, 0, 0, width, height, rgb("cover_bg"))
    rect(cover, 0, 0, Inches(0.14), height, rgb("cover_accent"))          # left accent spine
    rect(cover, Inches(1.15), Inches(2.15), Inches(0.075), Inches(2.45), rgb("cover_accent"))

    text(cover, Inches(1.5), Inches(2.05), Inches(10.4), Inches(1.8), title, 40, WHITE, bold=True, spacing=1.05)
    source_label = (content_model or {}).get("source_type") or "briefing"
    text(cover, Inches(1.5), Inches(3.95), Inches(10.4), Inches(0.5),
         f"Generated {artefact_type.replace('_', ' ')}  ·  {source_label}", 17,
         rgb("cover_sub"))

    if content_model and content_model.get("severity"):
        severity = str(content_model["severity"]).upper()
        pill = rect(cover, Inches(1.5), Inches(4.62), Inches(1.5), Inches(0.42), rgb("pill_fill"))
        pill.text_frame.word_wrap = False
        para = pill.text_frame.paragraphs[0]
        para.text = severity
        para.alignment = PP_ALIGN.CENTER
        run = para.runs[0]
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = rgb("pill_text")
        run.font.name = FONT
        pill.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

    text(cover, Inches(1.5), height - Inches(1.05), Inches(10), Inches(0.4),
         "One source · one content model · every deliverable", 11, rgb("cover_sub"))

    # --------------------------------------------------------------- slides
    slides = draft.get("slides") or []
    for index, slide_data in enumerate(slides, start=1):
        if isinstance(slide_data, str):
            slide_data = {"title": f"Slide {index}", "bullets": [slide_data]}

        page = prs.slides.add_slide(blank)
        rect(page, 0, 0, width, height, SLIDE_BG)

        eyebrow = (content_model or {}).get("source_type") or "briefing"
        slide_title = str(slide_data.get("title") or f"Slide {index}")
        layout = PPTX_LAYOUTS.get(resolve_pptx_template(options), "plain")

        if layout == "banded":
            # Full-bleed colour band carrying the title, plus an angular corner
            # shard sweeping in from the bottom right — a print-design device.
            band_height = Inches(2.30)
            rect(page, 0, 0, width, band_height, ACCENT)

            shard = page.shapes.add_shape(
                MSO_SHAPE.RIGHT_TRIANGLE,
                width - Inches(3.6), height - Inches(2.5), Inches(3.6), Inches(2.5),
            )
            shard.fill.solid()
            shard.fill.fore_color.rgb = ACCENT
            shard.line.fill.background()
            shard.shadow.inherit = False

            text(page, Inches(0.9), Inches(0.58), Inches(11.2), Inches(0.3),
                 f"{index:02d}   ·   {str(eyebrow).upper()}", 10, rgb("cover_sub"), bold=True)
            text(page, Inches(0.9), Inches(0.98), Inches(11.2), Inches(1.15),
                 slide_title, 34, WHITE, bold=True, spacing=1.03)
            body_top = band_height + Inches(0.55)
        elif layout == "sidebar":
            # Full-height accent spine down the left edge, content offset past it.
            rect(page, 0, 0, Inches(0.34), height, ACCENT)
            text(page, Inches(1.15), Inches(0.62), Inches(10), Inches(0.3),
                 f"{index:02d}   ·   {str(eyebrow).upper()}", 10, ACCENT, bold=True)
            text(page, Inches(1.15), Inches(1.02), Inches(10.8), Inches(0.9),
                 slide_title, 30, INK, bold=True, spacing=1.05)
            rect(page, Inches(1.15), Inches(1.95), Inches(1.2), Pt(3), ACCENT)
            body_top = Inches(2.45)
        else:
            text(page, Inches(0.9), Inches(0.62), Inches(10), Inches(0.3),
                 f"{index:02d}   ·   {str(eyebrow).upper()}", 10, ACCENT, bold=True)
            text(page, Inches(0.9), Inches(1.02), Inches(11.2), Inches(0.9),
                 slide_title, 30, INK, bold=True, spacing=1.05)
            rect(page, Inches(0.9), Inches(1.95), Inches(1.2), Pt(3), ACCENT)
            body_top = Inches(2.45)

        items = _as_list(slide_data.get("bullets"))
        notes = str(slide_data.get("speaker_notes") or "").strip()

        # A slide can come back from the model with a title and no bullets, which
        # renders as a bare heading on a white page. Fall back to the speaker note
        # so the slide carries content instead of looking broken.
        used_notes_as_body = False
        if not items and notes:
            items = [notes]
            used_notes_as_body = True

        if items:
            bullets(page, Inches(0.9), body_top, Inches(11.2), Inches(2.2), items)

        if notes and not used_notes_as_body:
            # The note is visible on the slide too, in a tinted rail, so a printed
            # handout carries the presenter's context. Placed below the bullet area
            # (which ends at 4.65") so it can never paint over the body text.
            rail = rect(page, Inches(0.9), Inches(5.05), Inches(11.2), Inches(1.15), rgb("note_bg"))
            frame = rail.text_frame
            frame.word_wrap = True
            frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            frame.margin_left = Inches(0.28)
            frame.margin_right = Inches(0.28)
            para = frame.paragraphs[0]
            para.text = f"Speaker note — {notes}"
            para.line_spacing = 1.25
            run = para.runs[0]
            run.font.size = Pt(11)
            run.font.italic = True
            run.font.color.rgb = MUTED
            run.font.name = FONT

            page.notes_slide.notes_text_frame.text = notes

        footer(page, index)

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def _pdf_text(value: str) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def render_pdf(artefact_type: str, draft: dict, content_model: dict | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    title = _title_for(artefact_type, draft, content_model)
    story: list = [Paragraph(_pdf_text(title), styles["Title"]), Spacer(1, 6 * mm)]

    for field in ARTEFACT_PROFILES[artefact_type]["fields"]:
        items = _as_list(draft.get(field))
        if not items:
            continue
        story.append(Paragraph(_pdf_text(_label(field)), styles["Heading2"]))
        if len(items) == 1:
            story.append(Paragraph(_pdf_text(items[0]), styles["BodyText"]))
        else:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(_pdf_text(item), styles["BodyText"])) for item in items],
                    bulletType="bullet",
                    start="•",
                )
            )
        story.append(Spacer(1, 4 * mm))

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=title, author="Content Transformation Engine")
    document.build(story)
    return buffer.getvalue()


def _timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def render_srt(draft: dict, *_) -> str:
    cues = _as_list(draft.get("subtitles")) or _as_list(draft.get("narration")) or _as_list(draft.get("script"))
    if not cues:
        return ""
    if any("-->" in cue for cue in cues):
        return "\n".join(cues).strip() + "\n"

    lines: list[str] = []
    cursor = 0.0
    for index, cue in enumerate(cues, start=1):
        duration = max(2.0, min(8.0, len(cue) / 15))
        lines.append(str(index))
        lines.append(f"{_timestamp(cursor)} --> {_timestamp(cursor + duration)}")
        lines.append(cue)
        lines.append("")
        cursor += duration
    return "\n".join(lines)


def render_payload(
    artefact_type: str, draft: dict, fmt: str, content_model: dict | None = None,
    options: dict | None = None,
) -> tuple[str | bytes, str]:
    """Return (payload, kind) where kind is "text" or "bytes"."""
    if fmt == "md":
        return render_markdown(artefact_type, draft, content_model), "text"
    if fmt == "txt":
        return render_plaintext(artefact_type, draft, content_model), "text"
    if fmt == "json":
        return render_json(draft), "text"
    if fmt == "srt":
        return render_srt(draft), "text"
    if fmt == "pdf":
        return render_pdf(artefact_type, draft, content_model), "bytes"
    if fmt == "pptx":
        return render_pptx(draft, content_model, artefact_type, options), "bytes"
    if fmt == "png":
        return render_infographic_png(draft, content_model, artefact_type, options), "bytes"
    raise ValueError(f"no renderer for format {fmt!r}")


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(name)).strip("-") or "run"


def write_artefact_files(
    run_id: str, artefacts: dict, content_model: dict | None = None, options: dict | None = None
) -> list[dict]:
    """Render every artefact to every configured format and write it to disk."""
    folder = get_artefacts_dir() / _safe_name(run_id)
    folder.mkdir(parents=True, exist_ok=True)

    written: list[dict] = []
    for artefact_type, draft in artefacts.items():
        profile = ARTEFACT_PROFILES.get(artefact_type)
        if not profile or not isinstance(draft, dict):
            continue
        formats = profile.get("render_formats") or [profile["export_ext"]]
        for fmt in formats:
            payload, kind = render_payload(artefact_type, draft, fmt, content_model, options)
            data = payload.encode("utf-8") if kind == "text" else payload
            path = folder / f"{artefact_type}.{fmt}"
            path.write_bytes(data)
            written.append(
                {
                    "type": artefact_type,
                    "ext": fmt,
                    "path": str(path),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return written


__all__ = [
    "render_infographic_png",
    "render_json",
    "render_linkedin_post",
    "render_markdown",
    "render_payload",
    "render_pdf",
    "render_plaintext",
    "render_pptx",
    "render_srt",
    "write_artefact_files",
]
