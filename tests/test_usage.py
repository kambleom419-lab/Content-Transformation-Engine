import pytest

from engine.tracing import traced_llm, tracing_enabled, tracing_status
from engine.usage import LEDGER, gemini_usage, openai_usage, track


@pytest.fixture(autouse=True)
def clear_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


class _GeminiMetadata:
    prompt_token_count = 120
    candidates_token_count = 40


class _GeminiResponse:
    usage_metadata = _GeminiMetadata()


def test_openai_usage_extracts_token_counts():
    payload = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    assert openai_usage(payload) == (10, 5)


def test_openai_usage_tolerates_missing_or_dirty_usage():
    assert openai_usage({}) == (0, 0)
    assert openai_usage({"usage": {"prompt_tokens": None}}) == (0, 0)
    assert openai_usage({"usage": {"prompt_tokens": "n/a"}}) == (0, 0)


def test_gemini_usage_extracts_token_counts():
    assert gemini_usage(_GeminiResponse()) == (120, 40)


def test_gemini_usage_tolerates_missing_metadata():
    assert gemini_usage(object()) == (0, 0)


def test_track_records_a_successful_call():
    with track("groq", "model-a", "generate_json") as entry:
        entry.prompt_tokens, entry.completion_tokens = 100, 50

    snapshot = LEDGER.snapshot()
    assert snapshot["calls"] == 1
    assert snapshot["errors"] == 0
    assert snapshot["prompt_tokens"] == 100
    assert snapshot["completion_tokens"] == 50
    assert snapshot["total_tokens"] == 150
    assert snapshot["by_provider"]["groq"]["calls"] == 1
    assert snapshot["by_operation"]["generate_json"]["calls"] == 1


def test_track_records_a_failure_and_still_raises():
    with pytest.raises(ValueError):
        with track("groq", "model-a", "generate_text"):
            raise ValueError("boom")

    snapshot = LEDGER.snapshot()
    assert snapshot["calls"] == 1
    assert snapshot["errors"] == 1
    assert snapshot["recent"][0]["ok"] is False
    assert snapshot["recent"][0]["latency_ms"] >= 0


def test_snapshot_aggregates_across_providers():
    with track("a", "m", "op"):
        pass
    with track("b", "m", "op"):
        pass

    snapshot = LEDGER.snapshot()
    assert snapshot["calls"] == 2
    assert set(snapshot["by_provider"]) == {"a", "b"}
    assert snapshot["by_operation"]["op"]["calls"] == 2


def test_tracing_is_off_by_default(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls__x")
    assert tracing_enabled() is False


def test_tracing_requires_an_api_key(monkeypatch):
    """Flag on but no key: stay off, rather than 401 on every background upload."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    assert tracing_enabled() is False
    assert tracing_status()["has_api_key"] is False


def test_tracing_enabled_with_flag_and_key(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls__x")
    assert tracing_enabled() is True


class _Adapter:
    name = "fake"
    model = "fake-model"
    vision_model = "fake-vision"

    @traced_llm("generate_text")
    def generate_text(self, prompt, parts=None):
        return f"text:{prompt}"

    @traced_llm("generate_json")
    def generate_json(self, prompt, json_schema=None, parts=None):
        return {"ok": True}


def test_traced_llm_is_transparent_when_tracing_is_off(monkeypatch):
    """Regression: the decorator must forward only the arguments each method accepts.
    An earlier version always passed json_schema, which broke generate_text()."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    adapter = _Adapter()

    assert adapter.generate_text("hi") == "text:hi"
    assert adapter.generate_text("hi", parts=[object()]) == "text:hi"
    assert adapter.generate_json("hi", json_schema={"type": "object"}) == {"ok": True}
    assert adapter.generate_json("hi") == {"ok": True}
