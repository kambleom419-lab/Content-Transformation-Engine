"""Smoke-test the real Gemini paths. Requires GEMINI_API_KEY in .env.

Run:  .venv\\Scripts\\python.exe tests\\smoke_gemini.py
Specifically exercises the parts the offline suite CANNOT: real text generation,
real schema-constrained JSON, and real vision (image bytes as a MediaPart).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import base64

from engine.config import get_api_key, get_model
from engine.llm import GeminiAdapter, MediaPart

# 1x1 red PNG — enough to prove the vision path sends bytes to the model.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def main() -> int:
    if not get_api_key():
        print("SKIP: GEMINI_API_KEY is empty in .env — paste your key there first.")
        return 0

    print(f"model: {get_model()}")
    llm = GeminiAdapter()

    print("\n[1] generate_text ...")
    out = llm.generate_text("Reply with exactly: PONG")
    print(f"    -> {out!r}")
    assert out, "empty text response"

    print("\n[2] generate_json (schema-constrained) ...")
    data = llm.generate_json(
        "Return a JSON object describing a security incident titled 'Mail Gateway RCE' "
        "with severity high and one recommended action.",
        json_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "low", "medium", "high", "critical"]},
                "recommended_actions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "severity", "recommended_actions"],
        },
    )
    print(f"    -> {data}")
    assert data.get("severity") in {"info", "low", "medium", "high", "critical"}, data

    print("\n[3] generate_text with image bytes (vision) ...")
    out = llm.generate_text(
        "Describe this image in one short sentence.",
        parts=[MediaPart(mime_type="image/png", data=TINY_PNG)],
    )
    print(f"    -> {out!r}")
    assert out, "empty vision response"

    print("\nALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
