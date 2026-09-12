import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
except ImportError:
    pass


def get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or None


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
