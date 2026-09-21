from __future__ import annotations
SOURCE_TYPES = ["advisory", "report", "article", "policy", "research", "announcement", "incident", "prompt", "image", "transcript"]
SEVERITIES = ["info", "low", "medium", "high", "critical"]

CONTENT_MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "severity": {"type": "string", "enum": SEVERITIES},
        "source_type": {"type": "string", "enum": SOURCE_TYPES},
        "language": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "source_ref": {"type": "string"}},
                "required": ["text", "source_ref"],
            },
        },
        "iocs": {"type": "array", "items": {"type": "string"}},
        "timeline": {"type": "array", "items": {"type": "string"}},
        "entities": {"type": "array", "items": {"type": "string"}},
        "key_messages": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "severity", "facts", "key_messages", "recommended_actions"],
}

ARTEFACT_PROFILES = {
    "advisory": {
        "label": "Structured Security Advisory",
        "fields": ["severity", "executive_summary", "affected_systems", "details", "iocs", "mitigations", "references"],
        "export_ext": "pdf",
        "render_formats": ["pdf"],
    },
    "executive_summary": {
        "label": "Executive Briefing",
        "fields": ["title", "summary", "key_points", "recommendations"],
        "export_ext": "pdf",
        "render_formats": ["pdf"],
    },
    "linkedin_post": {
        "label": "LinkedIn Post",
        "fields": ["headline", "body", "cta", "hashtags"],
        "export_ext": "txt",
        "render_formats": ["txt"],
    },
    "x_thread": {
        "label": "X / Twitter Thread",
        "fields": ["tweets"],
        "export_ext": "txt",
        "render_formats": ["txt"],
    },
    "presentation": {
        "label": "Presentation Slides + Speaker Notes",
        "fields": ["slides"],
        "export_ext": "pptx",
        "render_formats": ["pptx"],
    },
    "video_package": {
        "label": "Video Package",
        "fields": ["script", "storyboard", "scene_descriptions", "narration", "subtitles", "visual_recommendations"],
        # The production document an operator hands to a video team, plus the
        # machine format a video player consumes.
        "export_ext": "pdf",
        "render_formats": ["pdf", "srt"],
    },
    "infographic": {
        "label": "Infographic Content + Layout",
        "fields": ["content", "layout_recommendations", "key_messaging"],
        "export_ext": "png",
        "render_formats": ["png"],
    },
}

PARAM_KEYS = ["target_audience", "tone", "language", "level_of_detail", "communication_objective", "content_style"]

# Languages offered per artefact.
#
# `latin: True` means the PDF and PNG renderers can draw it with the fonts those
# libraries carry. Everything else is fine for .txt and .pptx — which is where
# the model's text goes unchanged — but needs a shaping engine for PDF/poster
# output, and Pillow and reportlab do not shape complex scripts.
LANGUAGES = [
    {"code": "English", "label": "English", "latin": True},
    {"code": "Hindi", "label": "हिन्दी (Hindi)", "latin": False},
    {"code": "Marathi", "label": "मराठी (Marathi)", "latin": False},
    {"code": "Bengali", "label": "বাংলা (Bengali)", "latin": False},
    {"code": "Tamil", "label": "தமிழ் (Tamil)", "latin": False},
    {"code": "Telugu", "label": "తెలుగు (Telugu)", "latin": False},
    {"code": "Kannada", "label": "ಕನ್ನಡ (Kannada)", "latin": False},
    {"code": "Gujarati", "label": "ગુજરાતી (Gujarati)", "latin": False},
    {"code": "Punjabi", "label": "ਪੰਜਾਬੀ (Punjabi)", "latin": False},
    {"code": "Urdu", "label": "اردو (Urdu)", "latin": False},
    {"code": "French", "label": "Français", "latin": True},
    {"code": "German", "label": "Deutsch", "latin": True},
    {"code": "Spanish", "label": "Español", "latin": True},
]

# Formats whose renderer draws the glyphs itself, so it is limited to scripts
# our bundled fonts and shaping support can handle.
SCRIPT_SENSITIVE_FORMATS = {"pdf", "png"}


def is_latin_language(name: str | None) -> bool:
    if not name:
        return True
    wanted = str(name).strip().lower()
    for entry in LANGUAGES:
        if entry["code"].lower() == wanted or entry["label"].lower() == wanted:
            return bool(entry["latin"])
    return True  # unknown language: assume ascii-safe rather than blocking it


def language_rule(language: str | None) -> str:
    """An explicit instruction, not just a parameter in a list."""
    name = str(language or "").strip()
    if not name or name.lower() in ("english", "en"):
        return ""
    return (
        f"- Write every field in {name}. Keep names, product and version numbers, "
        f"CVE identifiers, IP addresses, hashes and URLs exactly as they appear in "
        f"the content model — do not translate or transliterate them.\n"
    )


UNDERSTAND_INSTRUCTIONS = """You are an intelligence content analyst. Analyse the source corpus below and build the structured content model for it.

Rules:
- Extract ONLY facts explicitly stated in the source. Never invent facts, numbers, dates, IPs, hashes or IoCs.
- Every fact MUST carry the exact source_ref (in square brackets) of the block it came from.
- iocs: indicators of compromise only (IPs, domains, URLs, file hashes, CVEs, malware names).
- timeline: dated or ordered events, as short phrases.
- entities: organisations, products, threat actors, people, places.
- key_messages: 3-6 short statements an operator must communicate.
- recommended_actions: concrete, actionable steps.
- severity: judge from impact and exploitability stated in the source; use "info" if unclear.
- source_type: the closest label for the source document.
- Return a single JSON object only (no markdown fences, no commentary).
"""


def build_understand_prompt(corpus: list[dict], source_input: dict | None = None, sources: list[dict] | None = None) -> str:
    source_input = source_input or {}
    sources = sources or []
    blocks = "\n".join(f"[{c['source_ref']}]\n{c['text']}" for c in corpus)
    context = []
    if source_input.get("source_type"):
        context.append(f"declared source_type: {source_input['source_type']}")
    if source_input.get("source_language"):
        context.append(f"source language: {source_input['source_language']} (corpus is normalized to English)")
    if source_input.get("kind"):
        context.append(f"ingestion kind: {source_input['kind']}")
    context_line = f"\nSource context: {', '.join(context)}\n" if context else ""

    if len(sources) > 1:
        multi = "\n".join(
            f"- {s['source_id']} ({s['kind']}, {s['source_type']}, lang={s['language']}, {s['blocks']} blocks)"
            for s in sources
        )
        multi_line = (
            f"\nThis submission contains {len(sources)} sources:\n{multi}\n"
            "Attribute each fact to the source its source_ref belongs to. "
            "If sources disagree, prefer the most recent and note the conflict in key_messages.\n"
        )
    else:
        multi_line = ""

    return (
        f"{UNDERSTAND_INSTRUCTIONS}{context_line}{multi_line}"
        "=== SOURCE CORPUS ===\n"
        f"{blocks}\n"
        "=== END SOURCE CORPUS ==="
    )


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("value")
                if isinstance(text, str) and text.strip():
                    out.append(text.strip())
        return out
    return []


def repair_content_model(model: dict | None, fallback_source_type: str = "report", fallback_language: str = "en") -> dict:
    from engine.llm_utils import normalise_tree

    # Normalise identifier look-alikes (e.g. CVE-2026-4417 written with a
    # non-breaking hyphen) so every downstream artefact carries a CVE that
    # actually matches official records.
    model = normalise_tree(dict(model or {}))
    model["title"] = str(model.get("title") or "").strip()

    severity = str(model.get("severity") or "").strip().lower()
    model["severity"] = severity if severity in SEVERITIES else "medium"

    source_type = str(model.get("source_type") or "").strip().lower()
    model["source_type"] = source_type if source_type in SOURCE_TYPES else fallback_source_type

    model["language"] = str(model.get("language") or fallback_language).strip() or fallback_language

    for key in ("iocs", "timeline", "entities", "key_messages", "recommended_actions"):
        model[key] = _as_str_list(model.get(key))

    facts = []
    for fact in model.get("facts") or []:
        if isinstance(fact, dict) and str(fact.get("text") or "").strip():
            facts.append({"text": str(fact["text"]).strip(), "source_ref": str(fact.get("source_ref") or "").strip()})
        elif isinstance(fact, str) and fact.strip():
            facts.append({"text": fact.strip(), "source_ref": ""})
    model["facts"] = facts

    return model


def build_generation_prompt(artefact_type: str, content_model: dict, params: dict | None = None) -> str:
    profile = ARTEFACT_PROFILES[artefact_type]
    params = params or {}
    param_line = ", ".join(f"{k}={v}" for k, v in params.items() if v) or "default"
    return (
        f"You are a {profile['label'].lower()} writer for a national technical intelligence agency.\n"
        f"TARGET TYPE: {artefact_type}\n"
        f"Generation parameters: {param_line}\n"
        "Rules:\n"
        "- Use ONLY facts from the content model. Never invent numbers, dates or IoCs.\n"
        f"{language_rule(params.get('language'))}"
        "- Return a single JSON object only (no markdown fences, no commentary).\n"
        f"- Required keys: {', '.join(profile['fields'])}.\n"
        "- Include the requested structure (e.g. video: script/storyboard/scenes/narration/"
        "subtitles/visual recommendations).\n"
        "=== CONTENT MODEL ===\n"
        f"{json_dumps(content_model)}\n"
        "=== END CONTENT MODEL ==="
    )


def json_dumps(value) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False)
