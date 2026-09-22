import pytest

from engine.generate import (
    X_TWEET_LIMIT,
    build_artefact_json_schema,
    check_ioc_integrity,
    clamp_tweet,
    fact_check_draft,
    run_generate_and_check,
)


class FakeLLM:
    """Returns queued responses in order; raises if the queue runs out."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt, json_schema=None, parts=None):
        self.prompts.append(prompt)
        if not self.responses:
            raise RuntimeError("FakeLLM: no more queued responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_corpus(pairs):
    return [{"text": text, "source_ref": ref} for text, ref in pairs]


CONTENT_MODEL = {
    "title": "AcmeServer RCE",
    "severity": "high",
    "facts": [{"text": "AcmeServer versions before 4.2.1 allow remote code execution", "source_ref": "doc:p1"}],
    "iocs": ["CVE-2024-31337", "198.51.100.23"],
    "entities": ["AcmeServer"],
    "key_messages": ["Patch to 4.2.1 immediately"],
    "recommended_actions": ["Apply the vendor patch"],
}

CORPUS = make_corpus([
    ("AcmeServer versions before 4.2.1 allow remote code execution via a crafted request.", "doc:p1"),
    ("Organisations should patch to version 4.2.1 immediately to remain protected.", "doc:p2"),
])


def test_build_artefact_json_schema_marks_array_fields_correctly():
    schema = build_artefact_json_schema("linkedin_post")
    assert schema["properties"]["hashtags"]["type"] == "array"
    assert schema["properties"]["headline"]["type"] == "string"
    assert set(schema["required"]) == {"headline", "body", "cta", "hashtags"}


def test_build_artefact_json_schema_handles_slides_as_objects():
    schema = build_artefact_json_schema("presentation")
    assert schema["properties"]["slides"]["type"] == "array"
    assert schema["properties"]["slides"]["items"]["type"] == "object"


def test_fact_check_draft_marks_grounded_claim_supported():
    draft = {"body": "AcmeServer versions before 4.2.1 allow remote code execution via a crafted request path."}
    result = fact_check_draft(draft, CORPUS)
    assert result.supported >= 1
    assert result.support_ratio > 0


def test_fact_check_draft_marks_invented_claim_unsupported():
    draft = {"body": "The vendor's CEO personally flew to every customer site to apologize in person for this."}
    result = fact_check_draft(draft, CORPUS)
    assert result.unsupported >= 1
    assert result.support_ratio < 0.5


def test_check_ioc_integrity_passes_verified_ioc():
    draft = {"body": "Track CVE-2024-31337 and block 198.51.100.23 immediately."}
    flags = check_ioc_integrity(draft, CONTENT_MODEL["iocs"])
    assert flags == []


def test_check_ioc_integrity_flags_invented_ioc():
    draft = {"body": "Also watch for traffic from 203.0.113.99, a newly observed C2 server."}
    flags = check_ioc_integrity(draft, CONTENT_MODEL["iocs"])
    assert len(flags) == 1
    assert flags[0]["verdict"] == "unverified_ioc"
    assert flags[0]["claim"] == "203.0.113.99"


GOOD_DRAFT = {
    "headline": "Critical RCE in AcmeServer",
    "body": "AcmeServer versions before 4.2.1 allow remote code execution via a crafted request. Patch to version 4.2.1 immediately to remain protected.",
    "cta": "Patch now",
    "hashtags": ["#cybersecurity", "#infosec"],
}


def test_run_generate_and_check_happy_path():
    llm = FakeLLM([GOOD_DRAFT])
    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm)

    assert result["draft"]["headline"] == "Critical RCE in AcmeServer"
    assert result["meta"]["retries"] == 0
    assert result["meta"]["missing_fields"] == []
    assert result["meta"]["support_ratio"] > 0.5


def test_run_generate_and_check_retries_on_bad_json():
    llm = FakeLLM([RuntimeError("malformed"), GOOD_DRAFT])
    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm)
    assert result["meta"]["retries"] == 1


def test_run_generate_and_check_repairs_missing_fields():
    incomplete = {"headline": "Critical RCE", "body": "AcmeServer versions before 4.2.1 allow remote code execution."}
    repair_fill = {"cta": "Patch now", "hashtags": ["#infosec"]}
    llm = FakeLLM([incomplete, repair_fill])

    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm)

    assert result["draft"]["cta"] == "Patch now"
    assert result["draft"]["hashtags"] == ["#infosec"]
    assert result["meta"]["fields_repaired"] is True
    assert result["meta"]["missing_fields"] == []


def test_run_generate_and_check_flags_invented_ioc_in_final_draft():
    draft_with_bad_ioc = {**GOOD_DRAFT, "body": GOOD_DRAFT["body"] + " Also block 203.0.113.99."}
    llm = FakeLLM([draft_with_bad_ioc])
    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm, min_support_ratio=0.0)

    unverified = [v for v in result["verdicts"] if v["verdict"] == "unverified_ioc"]
    assert len(unverified) == 1
    assert unverified[0]["claim"] == "203.0.113.99"
    assert "203.0.113.99" in result["meta"]["unverified_iocs"]


def test_run_generate_and_check_regenerates_when_poorly_grounded_and_keeps_better_version():
    bad_draft = {
        "headline": "Breaking News",
        "body": "The vendor's CEO personally flew to every customer site to apologize for the outage caused by aliens.",
        "cta": "Read more",
        "hashtags": ["#news"],
    }
    better_draft = {**GOOD_DRAFT}
    llm = FakeLLM([bad_draft, better_draft])

    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm, min_support_ratio=0.6)

    assert result["meta"]["regenerated_for_grounding"] is True
    assert result["draft"]["headline"] == "Critical RCE in AcmeServer"
    assert result["meta"]["support_ratio"] > 0.5


def test_run_generate_and_check_keeps_original_if_regeneration_not_better():
    bad_draft = {
        "headline": "Breaking News",
        "body": "The vendor's CEO personally flew to every customer site to apologize for the outage caused by aliens.",
        "cta": "Read more",
        "hashtags": ["#news"],
    }
    also_bad_draft = {**bad_draft, "headline": "Still Bad News"}
    llm = FakeLLM([bad_draft, also_bad_draft])

    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm, min_support_ratio=0.6)

    assert result["meta"]["regenerated_for_grounding"] is False
    assert result["draft"]["headline"] == "Breaking News"


def test_run_generate_and_check_rejects_unknown_artefact_type():
    llm = FakeLLM([GOOD_DRAFT])
    with pytest.raises(ValueError):
        run_generate_and_check("not_a_real_type", CONTENT_MODEL, CORPUS, llm=llm)


PATCH_CORPUS = make_corpus([
    ("The vendor recommends patching the gateway within 72 hours of detection.", "doc:p3"),
])


def test_fact_check_flags_changed_number_despite_matching_wording():
    """Regression: the source says 72 hours, the draft says 9 hours. Every word
    matches, so pure token overlap marked it supported. Numbers must be checked."""
    draft = {"body": "The vendor recommends patching the gateway within 9 hours of detection."}
    result = fact_check_draft(draft, PATCH_CORPUS)

    assert result.supported == 0
    assert result.unverified == 1
    verdict = result.verdicts[0]
    assert verdict["verdict"] == "unverified_number"
    assert verdict["unverified_numbers"] == ["9"]
    assert verdict["citation"] == "doc:p3"


def test_fact_check_accepts_the_number_the_source_states():
    draft = {"body": "The vendor recommends patching the gateway within 72 hours of detection."}
    result = fact_check_draft(draft, PATCH_CORPUS)

    assert result.supported == 1
    assert result.unverified == 0


def test_unverified_number_lowers_support_ratio():
    draft = {"body": "The vendor recommends patching the gateway within 9 hours of detection."}
    result = fact_check_draft(draft, PATCH_CORPUS)
    assert result.support_ratio == 0.0


def test_tokens_excludes_stopwords():
    from engine.llm_utils import tokens

    assert "the" not in tokens("The vendor and the customer")
    assert "and" not in tokens("The vendor and the customer")
    assert "vendor" in tokens("The vendor and the customer")


def test_bare_ordinals_are_not_treated_as_facts():
    """Scene numbers and list markers are structure, not claims — real runs showed
    a storyboard's "1..5" being reported as five unverified facts."""
    from engine.generate import numbers

    assert numbers("Scene 1: show the gateway") == set()
    assert numbers("1/6 - patch immediately") == set()
    assert numbers("Shot 4") == set()


def test_factual_numbers_are_still_captured():
    from engine.generate import numbers

    assert numbers("patch within 9 hours") == {"9"}
    assert numbers("upgrade to version 3.2.1") == {"3.2.1"}
    assert numbers("exploited in 2026") == {"2026"}
    assert numbers("affecting 1,000 hosts") == {"1,000"}


def test_identifier_lookalikes_are_normalised():
    """Models write CVEs with a non-breaking hyphen, which will not match
    official records or survive a copy-paste search."""
    from engine.llm_utils import normalise_identifiers

    assert normalise_identifiers("CVE\u20112026\u20114417") == "CVE-2026-4417"
    assert normalise_identifiers("CVE\u20102026\u20104417") == "CVE-2026-4417"
    # an em dash in prose is legitimate punctuation and must survive
    assert normalise_identifiers("patch now \u2014 urgently") == "patch now \u2014 urgently"
    assert normalise_identifiers("3.2.1") == "3.2.1"


def test_generated_draft_has_normalised_identifiers():
    draft = {**GOOD_DRAFT, "body": GOOD_DRAFT["body"] + " Track CVE\u20112024\u201131337 now."}
    llm = FakeLLM([draft])
    result = run_generate_and_check("linkedin_post", CONTENT_MODEL, CORPUS, llm=llm, min_support_ratio=0.0)

    assert "CVE-2024-31337" in result["draft"]["body"]
    assert "\u2011" not in result["draft"]["body"]


def test_clamp_tweet_leaves_a_short_post_untouched():
    assert clamp_tweet("  short post  ") == "short post"


def test_clamp_tweet_shortens_an_over_limit_post_at_a_word_boundary():
    text = "word " * 80

    clamped = clamp_tweet(text)

    assert len(clamped) <= X_TWEET_LIMIT
    assert clamped.endswith("\u2026")
    assert not clamped[:-1].endswith(" ")


def test_run_generate_and_check_clamps_overlong_x_thread():
    overlong = "A" * (X_TWEET_LIMIT + 40)
    llm = FakeLLM([{"tweets": [overlong]}])

    result = run_generate_and_check("x_thread", CONTENT_MODEL, CORPUS, llm=llm, min_support_ratio=0.0)

    tweets = result["draft"]["tweets"]
    assert all(len(tweet) <= X_TWEET_LIMIT for tweet in tweets)
    assert tweets[0].startswith("A")