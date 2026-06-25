import pytest

from app.providers.prompts import (
    build_analysis_output,
    build_analysis_prompt,
    build_sarvam_analysis_prompt,
    extract_llm_content,
    extract_llm_finish_reason,
    normalize_analysis_data,
    parse_json_response,
    safe_parse_llm_json,
    validate_analysis_json,
)


def test_build_analysis_prompt_includes_transcript():
    prompt = build_analysis_prompt("Patient called about billing.")
    assert "Patient called about billing." in prompt
    assert "__TRANSCRIPT__" not in prompt
    assert '"notes"' in prompt
    assert "Security and scope rules" in prompt


def test_build_analysis_prompt_handles_empty_transcript():
    prompt = build_analysis_prompt("")
    assert "Security and scope rules" in prompt


def test_extract_llm_content_openai_shape():
    data = {
        "choices": [
            {"message": {"content": '{"sentiment": "neutral"}'}}
        ]
    }
    assert extract_llm_content(data) == '{"sentiment": "neutral"}'


def test_extract_llm_content_null_content():
    data = {"choices": [{"message": {"content": None}}]}
    assert extract_llm_content(data) == ""


def test_safe_parse_llm_json_with_prose_wrapper():
    text = 'Analysis complete.\n{"sentiment": "mixed", "summary": "ok", "confidence": 0.5}'
    parsed = safe_parse_llm_json(text)
    assert parsed.data is not None
    assert parsed.data["sentiment"] == "mixed"


def test_safe_parse_llm_json_invalid_preserves_raw():
    parsed = safe_parse_llm_json("not json at all")
    assert parsed.data is None
    assert parsed.error
    assert parsed.raw_text == "not json at all"


def test_parse_json_response_none_raises():
    with pytest.raises(ValueError, match="empty response"):
        parse_json_response(None)


def test_build_analysis_output_maps_fields():
    data = {
        "sentiment": "positive",
        "issues": ["delay"],
        "summary": "Call resolved quickly.",
        "actions": ["Follow up"],
        "resolution_status": "resolved",
        "confidence": 0.88,
        "notes": "Clear audio",
    }
    out = build_analysis_output(data, "sarvam_llm", 1.25)
    assert out.sentiment == "positive"
    assert out.key_issues == ["delay"]
    assert out.action_items == ["Follow up"]
    assert out.notes == "Clear audio"
    assert out.provider == "sarvam_llm"
    assert out.error is None


def test_validate_analysis_json_requires_lists():
    data = {
        "sentiment": "neutral",
        "summary": "ok",
        "resolution_status": "resolved",
        "confidence": 0.5,
        "notes": "",
    }
    validated, error = validate_analysis_json(data)
    assert validated is None
    assert "key_issues" in error or "issues" in error
