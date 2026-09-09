
CONTENT_MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "severity": {"type": "string", "enum": ["info", "low", "medium", "high", "critical"]},
        "source_type": {"type": "string"},
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
        "export_ext": "md",
    },
    "executive_summary": {
        "label": "Executive Briefing",
        "fields": ["title", "summary", "key_points", "recommendations"],
        "export_ext": "md",
    },
    "linkedin_post": {
        "label": "LinkedIn Post",
        "fields": ["headline", "body", "cta", "hashtags"],
        "export_ext": "txt",
    },
    "x_thread": {
        "label": "X / Twitter Thread",
        "fields": ["tweets"],
        "export_ext": "txt",
    },
    "presentation": {
        "label": "Presentation Slides + Speaker Notes",
        "fields": ["slides"],
        "export_ext": "json",
    },
    "video_package": {
        "label": "Video Package",
        "fields": ["script", "storyboard", "scene_descriptions", "narration", "subtitles", "visual_recommendations"],
        "export_ext": "json",
    },
    "infographic": {
        "label": "Infographic Content + Layout",
        "fields": ["content", "layout_recommendations", "key_messaging"],
        "export_ext": "md",
    },
}

PARAM_KEYS = ["target_audience", "tone", "language", "level_of_detail", "communication_objective", "content_style"]


def build_understand_prompt(corpus: list[dict]) -> str:
    blocks = "\n".join(f"[{c['source_ref']}]\n{c['text']}" for c in corpus)
    return (
        "You are an intelligence content analyst. Analyse the source corpus below and build "
        "the structured content model for it.\n"
        "Extract only facts that are explicitly stated. Never invent facts, numbers, dates, "
        "IPs or IoCs. Each fact must carry its source_ref.\n"
        "=== SOURCE CORPUS ===\n"
        f"{blocks}\n"
        "=== END SOURCE CORPUS ==="
    )


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
