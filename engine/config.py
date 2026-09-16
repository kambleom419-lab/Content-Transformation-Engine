import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
except ImportError:
    pass


def get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or None


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def get_fallback_chain() -> list[str]:
    """
    Ordered provider names, e.g. "groq,openrouter,ollama".

    Rotation is what actually survives a free-tier outage: a 429 is per-account,
    so swapping models inside one provider can never recover from it.
    """
    raw = os.getenv("LLM_FALLBACK_CHAIN") or os.getenv("LLM_PROVIDER") or "gemini"
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def get_use_stub() -> bool:
    return os.getenv("USE_STUB", "0").strip().lower() in {"1", "true", "yes", "on"}


def get_artefacts_dir() -> Path:
    raw = Path(os.getenv("ARTEFACTS_DIR", "artefacts"))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_api_host() -> str:
    return os.getenv("API_HOST", "127.0.0.1")


def get_api_port() -> int:
    return int(os.getenv("API_PORT", "8000"))
