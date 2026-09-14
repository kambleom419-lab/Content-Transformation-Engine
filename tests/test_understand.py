import json

import pytest

from engine.understand import (
    batch_corpus,
    dedupe_facts,
    dedupe_strings,
    extract_iocs_regex,
    ground_facts,
    run_understand,
)


class FakeLLM:
    """Returns queued responses in order; raises if the queue runs out or on demand."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, prompt, json_schema=None, parts=None):
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("FakeLLM: no more queued responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_corpus(pairs):
    return [{"text": text, "source_ref": ref} for text, ref in pairs]


# --- extract_iocs_regex ---------------------------------------------------

def test_extract_iocs_regex_finds_common_types():
    text = (
        "Contact admin@example.com about CVE-2024-12345. "
        "The C2 server is at 203.0.113.7 and evil-domain.com, "
        "see https://evil-domain.com/payload for details. "
        "SHA256: " + "a" * 64
    )
    iocs = extract_iocs_regex(text)
    assert "CVE-2024-12345" in iocs
    assert "203.0.113.7" in iocs
    assert any("evil-domain.com" in i for i in iocs)
    assert "admin@example.com" in iocs
    assert "a" * 64 in iocs


def test_extract_iocs_regex_no_false_positive_domains_from_urls():
    text = "See https://evil-domain.com/payload for details."
    iocs = extract_iocs_regex(text)
    # the domain should appear once (from the URL match), not duplicated as a bare domain
    domain_hits = [i for i in iocs if i.lower() == "evil-domain.com"]
    assert len(domain_hits) == 0  # consumed entirely inside the URL match
    assert any(i.startswith("https://evil-domain.com") for i in iocs)


# --- dedupe ----------------------------------------------------------------

def test_dedupe_strings_is_case_and_whitespace_insensitive():
    items = ["Patch systems", "patch   systems", "Patch systems.", "Rotate keys"]
    out = dedupe_strings(items)
    assert len(out) == 3  # "Patch systems." differs (trailing period) so stays distinct... see below
    # sanity: no exact-duplicate survives
    assert out.count("Patch systems") == 1


def test_dedupe_facts_keeps_first_occurrence():
    facts = [
        {"text": "Server was compromised", "source_ref": "doc:p1"},
        {"text": "server was compromised", "source_ref": "doc:p2"},
        {"text": "Different fact", "source_ref": "doc:p3"},
    ]
    out = dedupe_facts(facts)
    assert len(out) == 2
    assert out[0]["source_ref"] == "doc:p1"


# --- grounding ---------------------------------------------------------------

def test_ground_facts_accepts_valid_ref():
    corpus = make_corpus([("The attacker used phishing emails to gain access.", "doc:p1")])
    facts = [{"text": "The attacker used phishing emails", "source_ref": "doc:p1"}]
    result = ground_facts(facts, corpus)
    assert len(result.grounded) == 1
    assert result.grounded[0]["source_ref"] == "doc:p1"
    assert result.repaired_refs == 0


def test_ground_facts_repairs_hallucinated_ref_by_overlap():
    corpus = make_corpus([
        ("The attacker used phishing emails to gain initial access to the network.", "doc:p1"),
        ("Unrelated paragraph about quarterly budgets and staffing.", "doc:p2"),
    ])
    # model cited a ref that doesn't exist, but the text clearly matches p1
    facts = [{"text": "attacker used phishing emails to gain initial access", "source_ref": "doc:p99"}]
    result = ground_facts(facts, corpus)
    assert len(result.grounded) == 1
    assert result.grounded[0]["source_ref"] == "doc:p1"
    assert result.repaired_refs == 1


def test_ground_facts_drops_fact_with_no_match():
    corpus = make_corpus([("Completely unrelated content about weather patterns.", "doc:p1")])
    facts = [{"text": "The nuclear reactor melted down catastrophically", "source_ref": "doc:p1"}]
    result = ground_facts(facts, corpus)
    assert len(result.grounded) == 0
    assert len(result.dropped) == 1


# --- batching ----------------------------------------------------------------

def test_batch_corpus_splits_on_char_budget():
    corpus = make_corpus([("x" * 100, f"doc:p{i}") for i in range(10)])
    batches = batch_corpus(corpus, max_chars=250)
    assert len(batches) > 1
    for batch in batches:
        total = sum(len(c["text"]) for c in batch)
        assert total <= 250 + 100  # allows the single chunk that tips it over


def test_batch_corpus_single_batch_when_small():
    corpus = make_corpus([("short text", "doc:p1")])
    batches = batch_corpus(corpus, max_chars=9000)
    assert len(batches) == 1


# --- run_understand: retry behaviour -----------------------------------------

VALID_MODEL = {
    "title": "Test Advisory",
    "severity": "high",
    "source_type": "advisory",
    "language": "en",
    "facts": [{"text": "System X was breached via CVE-2024-1234", "source_ref": "doc:p1"}],
    "iocs": [],
    "timeline": [],
    "entities": ["System X"],
    "key_messages": ["Patch immediately"],
    "recommended_actions": ["Apply the vendor patch"],
}


def test_run_understand_happy_path_single_batch():
    corpus = make_corpus([("System X was breached via CVE-2024-1234 last week.", "doc:p1")])
    llm = FakeLLM([VALID_MODEL])
    model = run_understand(corpus, {"source_type": "advisory"}, [], llm)

    assert model["title"] == "Test Advisory"
    assert model["severity"] == "high"
    assert "CVE-2024-1234" in model["iocs"]  # regex safety net caught it too
    assert model["_meta"]["batches"] == 1
    assert model["_meta"]["retries"] == 0
    assert model["_meta"]["facts_grounded"] == 1


def test_run_understand_retries_on_bad_json_then_succeeds():
    corpus = make_corpus([("System X was breached via CVE-2024-1234 last week.", "doc:p1")])
    llm = FakeLLM([RuntimeError("malformed json"), VALID_MODEL])
    model = run_understand(corpus, {"source_type": "advisory"}, [], llm)

    assert model["title"] == "Test Advisory"
    assert model["_meta"]["retries"] == 1


def test_run_understand_raises_after_max_attempts_exhausted():
    corpus = make_corpus([("some text", "doc:p1")])
    llm = FakeLLM([RuntimeError("boom")] * 5)
    with pytest.raises(RuntimeError):
        run_understand(corpus, {"source_type": "advisory"}, [], llm, max_attempts=3)


def test_run_understand_batches_and_merges_large_corpus():
    corpus = make_corpus([(f"Fact about item {i} appears here in detail." * 3, f"doc:p{i}") for i in range(20)])

    expected_batches = batch_corpus(corpus, max_chars=500)
    assert len(expected_batches) > 1  # sanity check the fixture actually exercises batching

    partial = {**VALID_MODEL, "title": "Partial", "severity": "low"}
    merged = {**VALID_MODEL, "title": "Merged Final", "severity": "critical"}

    llm = FakeLLM([partial] * len(expected_batches) + [merged])
    model = run_understand(corpus, {"source_type": "report"}, [], llm, max_chars_per_batch=500)

    assert model["title"] == "Merged Final"
    assert model["severity"] == "critical"
    assert model["_meta"]["batches"] == len(expected_batches)


def test_run_understand_drops_ungrounded_facts_and_reports_them():
    corpus = make_corpus([("Only real content about network firewalls is here.", "doc:p1")])
    bad_model = {
        **VALID_MODEL,
        "facts": [
            {"text": "Only real content about network firewalls", "source_ref": "doc:p1"},
            {"text": "The president personally called the CEO at midnight", "source_ref": "doc:p1"},
        ],
    }
    llm = FakeLLM([bad_model])
    model = run_understand(corpus, {"source_type": "report"}, [], llm)

    assert len(model["facts"]) == 1
    assert model["_meta"]["facts_dropped_ungrounded"] == 1