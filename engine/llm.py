import json
import os
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def generate_json(self, prompt: str, json_schema: dict | None = None) -> dict:
        raise NotImplementedError


class GeminiAdapter(LLMProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

    def generate_json(self, prompt: str, json_schema: dict | None = None) -> dict:
        from google import genai

        client = genai.Client(api_key=self.api_key)
        config = {"temperature": 0.2}
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = json_schema
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)


class StubAdapter(LLMProvider):
    name = "stub"

    def generate_json(self, prompt: str, json_schema: dict | None = None) -> dict:
        if json_schema is not None:
            return {key: f"<stub> {key}" for key in json_schema.get("properties", {})}
        return {"output": "<stub> no schema"}
