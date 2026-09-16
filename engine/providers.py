"""
OpenAI-compatible providers and the rotating provider that fails over between them.

Groq, OpenRouter, Ollama and most other hosts speak the same
`/v1/chat/completions` shape, so a single adapter covers all of them — only the
base URL, key and model differ. That is what makes provider rotation cheap.

The pipeline always talks to ONE LLMProvider. RotatingProvider implements the
same interface and shifts between backends per *call*, because a run makes many
calls (understand, then one per artefact, plus OCR batches) and a single 429
must not kill the whole run.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import httpx

from engine import config
from engine.llm import LLMProvider, MediaPart, StubAdapter, _strip_fences, guess_mime


class ProviderUnavailable(RuntimeError):
    """Upstream is overloaded or unreachable — worth trying the next provider."""


class ProviderQuotaExceeded(RuntimeError):
    """This account's quota or rate limit is exhausted — cool down and move on."""


class ProviderAuthError(RuntimeError):
    """Credentials are wrong — disable this provider for the session."""


class ProviderRequestError(RuntimeError):
    """The request itself is invalid — rotating will not help."""


def _part_bytes(part: MediaPart) -> tuple[bytes, str]:
    mime = part.mime_type or (guess_mime(part.path) if part.path else "application/octet-stream")
    if part.data is not None:
        return part.data, mime
    if part.path:
        return Path(part.path).read_bytes(), mime
    raise ProviderRequestError("media part has neither data nor path")


def _data_url(part: MediaPart) -> str:
    data, mime = _part_bytes(part)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _is_media(part: MediaPart) -> bool:
    mime = part.mime_type or (guess_mime(part.path) if part.path else "")
    return mime.startswith("audio/") or mime.startswith("video/")


class OpenAICompatAdapter(LLMProvider):
    """
    One provider speaking the OpenAI chat-completions dialect.

    vision_model  — used instead of `model` when the call carries images.
    transcribe_model — when set, audio/video parts route to /audio/transcriptions
                       instead of the chat endpoint.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        vision_model: str | None = None,
        transcribe_model: str | None = None,
        extra_headers: dict | None = None,
        timeout: float = 240.0,
        supports_json_schema: bool = True,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vision_model = vision_model or None
        self.transcribe_model = transcribe_model or None
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.timeout = timeout
        self.supports_json_schema = supports_json_schema

    @property
    def supports_vision(self) -> bool:
        return bool(self.vision_model)

    @property
    def supports_audio(self) -> bool:
        return bool(self.transcribe_model)

    def _headers(self, json_body: bool = True) -> dict:
        headers = dict(self.extra_headers)
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _raise_for_status(self, response: httpx.Response, what: str) -> None:
        if response.status_code == 429:
            raise ProviderQuotaExceeded(f"{self.name}: quota/rate limit ({response.text[:200]})")
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"{self.name}: credentials rejected ({response.status_code})")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"{self.name}: upstream {response.status_code} ({response.text[:200]})")
        if response.status_code >= 400:
            raise ProviderRequestError(f"{self.name}: {what} failed {response.status_code} ({response.text[:300]})")

    def _post(self, path: str, body: dict) -> httpx.Response:
        try:
            response = httpx.post(
                f"{self.base_url}{path}", headers=self._headers(), json=body, timeout=self.timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"{self.name}: timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name}: transport error ({exc})") from exc
        self._raise_for_status(response, "chat completion")
        return response

    def _content(self, prompt: str, parts: list[MediaPart] | None):
        if not parts:
            return prompt
        blocks: list[dict] = [{"type": "text", "text": prompt}]
        for part in parts:
            blocks.append({"type": "image_url", "image_url": {"url": _data_url(part)}})
        return blocks

    def _chat(self, prompt: str, json_schema: dict | None, parts: list[MediaPart] | None) -> str:
        model = self.vision_model if parts else self.model
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": self._content(prompt, parts)}],
            "temperature": 0.2,
        }
        if json_schema:
            if self.supports_json_schema:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "strict": False, "schema": json_schema},
                }
            else:
                body["response_format"] = {"type": "json_object"}

        response = self._post("/chat/completions", body)
        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable(f"{self.name}: unexpected response shape ({str(payload)[:200]})") from exc

    def _transcribe(self, parts: list[MediaPart]) -> str:
        chunks: list[str] = []
        for part in parts:
            data, mime = _part_bytes(part)
            filename = Path(part.path).name if part.path else f"audio.{mime.split('/')[-1]}"
            try:
                response = httpx.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=self._headers(json_body=False),
                    data={"model": self.transcribe_model, "response_format": "text"},
                    files={"file": (filename, data, mime)},
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                raise ProviderUnavailable(f"{self.name}: transcription timed out") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f"{self.name}: transcription transport error ({exc})") from exc
            self._raise_for_status(response, "transcription")
            chunks.append(response.text.strip())
        return "\n\n".join(chunk for chunk in chunks if chunk)

    def generate_json(
        self, prompt: str, json_schema: dict | None = None, parts: list[MediaPart] | None = None
    ) -> dict:
        text = self._chat(prompt, json_schema, parts)
        stripped = _strip_fences(text).strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            start, end = stripped.find("{"), stripped.rfind("}")
            if start == -1 or end <= start:
                raise ProviderUnavailable(f"{self.name}: response was not JSON ({stripped[:200]})")
            parsed = json.loads(stripped[start : end + 1])
        if not isinstance(parsed, dict):
            raise ProviderUnavailable(f"{self.name}: expected a JSON object, got {type(parsed).__name__}")
        return parsed

    def generate_text(self, prompt: str, parts: list[MediaPart] | None = None) -> str:
        if parts and self.transcribe_model and any(_is_media(part) for part in parts):
            return self._transcribe(parts)
        if parts and not self.supports_vision:
            raise ProviderRequestError(f"{self.name}: no vision model configured for image input")
        return self._chat(prompt, None, parts)


class RotatingProvider(LLMProvider):
    """Fail over between providers, per call, with per-provider cooldowns."""

    def __init__(self, providers: list[LLMProvider], cooldown_s: float = 60.0):
        if not providers:
            raise ValueError("RotatingProvider needs at least one provider")
        self.providers = providers
        self.cooldown_s = cooldown_s
        self._cooldowns: dict[str, float] = {}
        self._disabled: set[str] = set()
        self._preferred = providers[0].name
        self.last_used: str | None = None

    @property
    def name(self) -> str:
        return "rotating(" + ",".join(provider.name for provider in self.providers) + ")"

    @property
    def events(self) -> list[dict]:
        return [{"provider": name, "cooldown_until": until} for name, until in self._cooldowns.items()]

    def _capable(self, provider: LLMProvider, needs_vision: bool, needs_audio: bool) -> bool:
        if needs_vision and not getattr(provider, "supports_vision", False):
            return False
        if needs_audio and not getattr(provider, "supports_audio", False):
            return False
        return True

    def _candidates(self, parts: list[MediaPart] | None) -> list[LLMProvider]:
        needs_vision = bool(parts) and not any(_is_media(part) for part in (parts or []))
        needs_audio = bool(parts) and any(_is_media(part) for part in (parts or []))
        now = time.monotonic()

        capable = [
            provider
            for provider in self.providers
            if provider.name not in self._disabled and self._capable(provider, needs_vision, needs_audio)
        ]
        ready = [provider for provider in capable if self._cooldowns.get(provider.name, 0) <= now]
        # Prefer the provider that worked last (sticky), then keep the configured order.
        return sorted(ready or capable, key=lambda p: 0 if p.name == self._preferred else 1)

    def _call(self, method: str, *args, **kwargs):
        candidates = self._candidates(kwargs.get("parts"))
        if not candidates:
            raise ProviderUnavailable("no provider can serve this request (check capability flags)")

        last_error: Exception | None = None
        for provider in candidates:
            try:
                result = getattr(provider, method)(*args, **kwargs)
            except ProviderAuthError as exc:
                self._disabled.add(provider.name)
                last_error = exc
                continue
            except ProviderQuotaExceeded as exc:
                self._cooldowns[provider.name] = time.monotonic() + self.cooldown_s
                last_error = exc
                continue
            except ProviderUnavailable as exc:
                self._cooldowns[provider.name] = time.monotonic() + min(self.cooldown_s, 20.0)
                last_error = exc
                continue
            self._preferred = provider.name
            self.last_used = provider.name
            return result

        raise last_error or ProviderUnavailable("all providers failed")

    def generate_json(
        self, prompt: str, json_schema: dict | None = None, parts: list[MediaPart] | None = None
    ) -> dict:
        return self._call("generate_json", prompt, json_schema=json_schema, parts=parts)

    def generate_text(self, prompt: str, parts: list[MediaPart] | None = None) -> str:
        return self._call("generate_text", prompt, parts=parts)


def _build_provider(name: str) -> LLMProvider | None:
    if name == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            return None
        return OpenAICompatAdapter(
            name="groq",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            vision_model=os.getenv("GROQ_VISION_MODEL") or None,
            transcribe_model=os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo"),
            api_key=key,
        )

    if name == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            return None
        return OpenAICompatAdapter(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            model=os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.2:free"),
            vision_model=os.getenv("OPENROUTER_VISION_MODEL", "google/gemma-4-31b-it:free"),
            api_key=key,
            extra_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost:3000"),
                "X-Title": "Content Transformation Engine",
            },
        )

    if name == "ollama":
        base = os.getenv("OLLAMA_BASE_URL")
        if not base:
            return None
        return OpenAICompatAdapter(
            name="ollama",
            base_url=base,
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            vision_model=os.getenv("OLLAMA_VISION_MODEL") or None,
            api_key=None,
            supports_json_schema=False,
        )

    if name == "gemini":
        from engine.llm import GeminiAdapter

        try:
            return GeminiAdapter()
        except Exception:
            return None

    if name == "stub":
        return StubAdapter()

    return None


def build_llm_provider() -> LLMProvider:
    """Assemble the configured provider chain (falls back to the stub offline)."""
    names = config.get_fallback_chain()
    providers = [provider for provider in (_build_provider(name) for name in names) if provider is not None]

    if not providers:
        return StubAdapter()
    if len(providers) == 1:
        return providers[0]
    return RotatingProvider(providers, cooldown_s=float(os.getenv("LLM_COOLDOWN_S", "60")))


__all__ = [
    "OpenAICompatAdapter",
    "ProviderAuthError",
    "ProviderQuotaExceeded",
    "ProviderRequestError",
    "ProviderUnavailable",
    "RotatingProvider",
    "build_llm_provider",
]
