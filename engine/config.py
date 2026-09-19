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


def get_max_concurrent_branches() -> int:
    """
    Cap on how many fan-out branches may run at once.

    Parallelism is a latency optimisation that costs quota: N selected outputs
    means N simultaneous provider requests. On the free tiers in use here that
    matters —

      * Groq allows roughly 30 requests/minute, so a burst is usually fine.
      * OpenRouter's shared free pool throttles aggressively and is the fragile
        one, especially when several branches land on it during a fallback.

    Selecting all 7 artefacts therefore fires 7 concurrent requests. Raising the
    cap buys latency; it must stay below what the weakest provider in the chain
    will tolerate. Raising it without headroom turns a working demo into a 429.
    """
    try:
        return max(1, int(os.getenv("MAX_CONCURRENT_BRANCHES", "3")))
    except ValueError:
        return 3


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
