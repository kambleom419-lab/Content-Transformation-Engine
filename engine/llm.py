from __future__ import annotations
import json
import mimetypes
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRYABLE_HINTS = ("unavailable", "high demand", "overloaded", "rate limit", "quota", "try again")


@dataclass
class MediaPart:
    mime_type: str
    data: bytes | None = None
    path: str | None = None


def guess_mime(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def generate_json(
        self, prompt: str, json_schema: dict | None = None, parts: list[MediaPart] | None = None
    ) -> dict:
        raise NotImplementedError

    def generate_text(self, prompt: str, parts: list[MediaPart] | None = None) -> str:
        raise NotImplementedError(f"{type(self).__name__} does not support generate_text")


class GeminiAdapter(LLMProvider):
    name = "gemini"
    supports_vision = True
    supports_audio = True
    FILE_POLL_INTERVAL_S = 2
    FILE_POLL_ATTEMPTS = 60
    MAX_ATTEMPTS = 4
    BASE_DELAY_S = 1.5

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from engine.config import get_api_key, get_model

        self.model = model or get_model()
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set (add it to .env — see .env.example)")

    def _client(self):
        from google import genai

        return genai.Client(api_key=self.api_key)

    def _model_chain(self) -> list[str]:
        raw = os.getenv("GEMINI_FALLBACK_MODELS", "")
        extras = [m.strip() for m in raw.split(",") if m.strip()]
        chain = [self.model]
        for model in extras:
            if model not in chain:
                chain.append(model)
        return chain

    def _upload_and_wait(self, client, path: str):
        uploaded = client.files.upload(file=path)
        for _ in range(self.FILE_POLL_ATTEMPTS):
            state = str(getattr(uploaded, "state", "") or "")
            if state.endswith("ACTIVE") or not state:
                break
            time.sleep(self.FILE_POLL_INTERVAL_S)
            uploaded = client.files.get(name=uploaded.name)
        return uploaded

    def _build_contents(self, client, prompt: str, parts: list[MediaPart] | None):
        from google.genai import types as genai_types

        contents: list = [prompt]
        for part in parts or []:
            if part.path:
                contents.append(self._upload_and_wait(client, part.path))
            elif part.data is not None:
                contents.append(genai_types.Part.from_bytes(data=part.data, mime_type=part.mime_type))
        return contents

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code in RETRYABLE_STATUS:
            return True
        message = str(exc).lower()
        return any(hint in message for hint in RETRYABLE_HINTS)

    def _generate(self, client, contents, config: dict):
        last_exc: Exception | None = None
        for model in self._model_chain():
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    return client.models.generate_content(model=model, contents=contents, config=config)
                except Exception as exc:
                    last_exc = exc
                    if not self._is_retryable(exc):
                        raise
                    if attempt < self.MAX_ATTEMPTS - 1:
                        delay = self.BASE_DELAY_S * (2**attempt) + random.uniform(0, 0.5)
                        time.sleep(delay)
        raise RuntimeError(f"Gemini unavailable after retries across {self._model_chain()}: {last_exc}")

    def generate_text(self, prompt: str, parts: list[MediaPart] | None = None) -> str:
        client = self._client()
        response = self._generate(
            client,
            self._build_contents(client, prompt, parts),
            {"temperature": 0.2, "automatic_function_calling": {"disable": True}},
        )
        return (response.text or "").strip()

    def generate_json(
        self, prompt: str, json_schema: dict | None = None, parts: list[MediaPart] | None = None
    ) -> dict:
        client = self._client()
        config: dict = {"temperature": 0.2, "automatic_function_calling": {"disable": True}}
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = json_schema
        contents = self._build_contents(client, prompt, parts) if parts else prompt
        response = self._generate(client, contents, config)
        return json.loads(_strip_fences((response.text or "").strip()))


class StubAdapter(LLMProvider):
    name = "stub"
    supports_vision = True
    supports_audio = True

    def generate_text(self, prompt: str, parts: list[MediaPart] | None = None) -> str:
        tag = f"[stub:{len(parts)} parts]" if parts else "[stub]"
        first_line = prompt.strip().splitlines()[0][:80] if prompt.strip() else ""
        return f"{tag} {first_line}"

    def generate_json(
        self, prompt: str, json_schema: dict | None = None, parts: list[MediaPart] | None = None
    ) -> dict:
        if json_schema is not None:
            return {key: f"<stub> {key}" for key in json_schema.get("properties", {})}
        return {"output": "<stub> no schema"}


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        return text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return text
