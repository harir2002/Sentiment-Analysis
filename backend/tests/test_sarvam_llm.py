import pytest

from app.providers.prompts import (
    build_sarvam_analysis_prompt,
    extract_llm_finish_reason,
    normalize_analysis_data,
    validate_analysis_json,
)
from app.providers.sarvam_llm import (
    build_sarvam_llm_payload,
    resolve_sarvam_max_tokens,
    shorten_transcript_for_sarvam,
)


def test_build_sarvam_llm_payload_structure():
    payload = build_sarvam_llm_payload("sarvam-30b", "Patient asked about billing.", max_tokens=4096)
    assert payload["model"] == "sarvam-30b"
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 4096
    assert payload["max_tokens"] <= 4096
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "Patient asked about billing." in payload["messages"][1]["content"]
    assert '"issues"' in payload["messages"][1]["content"]
    assert "Never return empty content" in payload["messages"][0]["content"]


def test_build_sarvam_llm_payload_clamps_excessive_max_tokens(monkeypatch):
    monkeypatch.setenv("SARVAM_LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("SARVAM_LLM_PLAN_TIER", "starter")
    payload = build_sarvam_llm_payload("sarvam-30b", "hello", max_tokens=8192)
    assert payload["max_tokens"] == 4096


def test_build_sarvam_analysis_prompt_retry_suffix():
    base = build_sarvam_analysis_prompt("hello")
    retry = build_sarvam_analysis_prompt("hello", retry=True)
    assert len(retry) > len(base)
    assert "previous response was empty" in retry


def test_extract_llm_finish_reason_length():
    data = {"choices": [{"finish_reason": "length", "message": {"content": None}}]}
    assert extract_llm_finish_reason(data) == "length"


def test_validate_analysis_json_accepts_issues_and_actions():
    data = {
        "sentiment": "neutral",
        "summary": "Brief summary.",
        "issues": ["billing delay"],
        "actions": ["call back"],
        "resolution_status": "partially_resolved",
        "confidence": 0.7,
        "notes": "",
    }
    validated, error = validate_analysis_json(data)
    assert error is None
    assert validated is not None
    assert validated["key_issues"] == ["billing delay"]
    assert validated["action_items"] == ["call back"]


def test_validate_analysis_json_rejects_missing_summary():
    data = {
        "sentiment": "neutral",
        "summary": "",
        "issues": [],
        "actions": [],
        "resolution_status": "unresolved",
        "confidence": 0.5,
        "notes": "",
    }
    validated, error = validate_analysis_json(data)
    assert validated is None
    assert "summary" in error


def test_validate_analysis_json_rejects_none_root():
    validated, error = validate_analysis_json(None)
    assert validated is None
    assert error


def test_normalize_analysis_data_maps_aliases():
    out = normalize_analysis_data({"issues": ["a"], "actions": ["b"]})
    assert out["key_issues"] == ["a"]
    assert out["action_items"] == ["b"]


def test_resolve_sarvam_max_tokens_never_exceeds_starter_cap(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("SARVAM_LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("SARVAM_LLM_PLAN_TIER", "starter")
    settings = Settings()
    assert settings.sarvam_llm_token_limit == 4096
    assert resolve_sarvam_max_tokens(attempt=0) == 4096
    assert resolve_sarvam_max_tokens(attempt=2) == 4096


def test_shorten_transcript_for_sarvam_on_retry():
    transcript = "x" * 20000
    first = shorten_transcript_for_sarvam(transcript, attempt=0, max_chars=12000)
    second = shorten_transcript_for_sarvam(transcript, attempt=1, max_chars=12000)
    assert len(first) <= 12000
    assert len(second) < len(first)
    assert "shortened" in second
