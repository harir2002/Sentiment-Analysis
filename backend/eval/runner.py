"""Offline evaluation and regression checks for guardrails and analysis schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.providers.prompts import validate_analysis_json
from app.services.guardrails import (
    detect_prompt_injection,
    mask_pii,
    prepare_transcript_for_analysis,
    sanitize_analysis_dict,
    validate_transcript_for_analysis,
)

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "analysis_cases.json"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def evaluate_guardrails(case: dict) -> list[str]:
    """Return list of failure messages (empty = pass)."""
    failures: list[str] = []
    transcript = case["transcript"]

    injection = detect_prompt_injection(transcript)
    if case.get("category") == "security" and not injection:
        failures.append("expected injection patterns to be detected")

    err = validate_transcript_for_analysis(transcript)
    if err and case.get("category") != "noisy":
        failures.append(f"transcript rejected: {err}")

    wrapped, meta = prepare_transcript_for_analysis(transcript)
    if "<<<CALL_TRANSCRIPT>>>" not in wrapped:
        failures.append("transcript not wrapped in delimiters")

    if case.get("category") == "security" and "injection_triggers" not in meta:
        failures.append("missing injection metadata")

    return failures


def evaluate_mock_analysis(case: dict) -> list[str]:
    """Validate schema enforcement on synthetic LLM-shaped output."""
    failures: list[str] = []
    sentiment = case.get("expected_sentiment", "neutral")
    resolution = case.get("expected_resolution", "unresolved")

    mock = sanitize_analysis_dict(
        {
            "sentiment": sentiment,
            "summary": (
                "Call about patient billing inquiry."
                if case.get("category") == "security"
                else f"Call about: {transcript_preview(case['transcript'])}"
            ),
            "key_issues": ["billing"] if "billing" in case["transcript"].lower() else [],
            "action_items": ["follow up"],
            "resolution_status": resolution,
            "confidence": max(case.get("min_confidence", 0.5), 0.75),
            "notes": "",
        }
    )

    validated, error = validate_analysis_json(mock)
    if error or validated is None:
        failures.append(f"schema validation failed: {error}")

    if validated and validated.get("sentiment") != sentiment:
        failures.append(f"sentiment clamp mismatch: {validated.get('sentiment')}")

    for forbidden in case.get("must_not_leak", []):
        summary = (mock.get("summary") or "").lower()
        if forbidden.lower() in summary:
            failures.append(f"forbidden phrase in summary: {forbidden}")

    return failures


def evaluate_pii_masking() -> list[str]:
    failures: list[str] = []
    sample = "Call from 9876543210 about MRN-12345 at john@clinic.com"
    masked = mask_pii(sample)
    for token in ("9876543210", "MRN-12345", "john@clinic.com"):
        if token in masked:
            failures.append(f"PII not masked: {token}")
    return failures


def transcript_preview(text: str, max_len: int = 80) -> str:
    return " ".join(text.split())[:max_len]


def run_all_evaluations() -> dict[str, Any]:
    cases = load_cases()
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    pii_failures = evaluate_pii_masking()
    if pii_failures:
        results.append({"id": "pii_masking", "passed": False, "failures": pii_failures})
        failed += 1
    else:
        results.append({"id": "pii_masking", "passed": True, "failures": []})
        passed += 1

    for case in cases:
        failures = evaluate_guardrails(case) + evaluate_mock_analysis(case)
        ok = not failures
        results.append({"id": case["id"], "category": case["category"], "passed": ok, "failures": failures})
        if ok:
            passed += 1
        else:
            failed += 1

    return {
        "total": passed + failed,
        "passed": passed,
        "failed": failed,
        "success": failed == 0,
        "results": results,
    }


if __name__ == "__main__":
    report = run_all_evaluations()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["success"] else 1)
