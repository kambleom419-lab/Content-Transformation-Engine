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
        # Models often number their own tweets ("1/ ..."). Don't number twice.
        if any(re.match(r"^\s*\d+\s*[/.)]", tweet) for tweet in tweets):
            return "\n\n".join(tweets).rstrip() + "\n"
        total = len(tweets)
        return "\n\n".join(f"{i}/{total}\n{tweet}" for i, tweet in enumerate(tweets, 1)) + "\n"

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


def render_pptx(draft: dict, content_model: dict | None = None, artefact_type: str = "presentation") -> bytes:
    from pptx import Presentation

    slides = draft.get("slides") or []
    prs = Presentation()

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = _title_for(artefact_type, draft, content_model)
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = "Generated by the Content Transformation Engine"

    for index, slide in enumerate(slides, start=1):
        if isinstance(slide, str):
            slide = {"title": f"Slide {index}", "bullets": [slide]}

        page = prs.slides.add_slide(prs.slide_layouts[1])
        page.shapes.title.text = str(slide.get("title") or f"Slide {index}")

        bullets = _as_list(slide.get("bullets"))
        frame = page.placeholders[1].text_frame
        frame.clear()
        for position, bullet in enumerate(bullets):
            paragraph = frame.paragraphs[0] if position == 0 else frame.add_paragraph()
            paragraph.text = bullet
            paragraph.level = 0

        notes = slide.get("speaker_notes")
        if notes and str(notes).strip():
            page.notes_slide.notes_text_frame.text = str(notes)

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
    artefact_type: str, draft: dict, fmt: str, content_model: dict | None = None
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
        return render_pptx(draft, content_model, artefact_type), "bytes"
    raise ValueError(f"no renderer for format {fmt!r}")


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(name)).strip("-") or "run"


def write_artefact_files(run_id: str, artefacts: dict, content_model: dict | None = None) -> list[dict]:
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
            payload, kind = render_payload(artefact_type, draft, fmt, content_model)
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
