"""AI guardrails: input validation, prompt-injection defense, PII masking, output sanitization."""
from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import get_settings
from app.models.schemas import AnalysisResult, ProviderResult
from app.services.recommended_action import enrich_analysis

logger = logging.getLogger(__name__)

TRANSCRIPT_START = "<<<CALL_TRANSCRIPT>>>"
TRANSCRIPT_END = "<<<END_CALL_TRANSCRIPT>>>"
TRANSCRIPT_SHORTENED_MARKER = "\n\n[... transcript shortened for analysis ...]\n\n"

VALID_SENTIMENTS = frozenset({"positive", "neutral", "negative", "mixed"})
VALID_RESOLUTION_STATUSES = frozenset(
    {"resolved", "partially_resolved", "unresolved", "escalated"}
)

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_prior_instructions",
        re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)"),
    ),
    (
        "disregard_system",
        re.compile(r"(?i)disregard\s+(the\s+)?(system|instructions?|rules?)"),
    ),
    (
        "role_override",
        re.compile(r"(?i)you\s+are\s+now\s+(a|an|the)\s+"),
    ),
    (
        "system_prompt_injection",
        re.compile(r"(?i)(^|\n)\s*system\s*:\s*"),
    ),
    (
        "assistant_prompt_injection",
        re.compile(r"(?i)(^|\n)\s*assistant\s*:\s*"),
    ),
    (
        "jailbreak_dan",
        re.compile(r"(?i)\bDAN\b|\bjailbreak\b|\bdo\s+anything\s+now\b"),
    ),
    (
        "output_format_override",
        re.compile(r"(?i)return\s+(only\s+)?(plain\s+text|markdown|html|xml)\s"),
    ),
    (
        "delimiter_breakout",
        re.compile(re.escape(TRANSCRIPT_START) + r"|" + re.escape(TRANSCRIPT_END)),
    ),
]

_PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(?\d{2,4}\)?[\s.-]?)?"
    r"\d{3}[\s.-]?\d{4}"
    r"(?!\d)"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
_MEDICAL_ID_PATTERN = re.compile(
    r"(?i)\b(?:MRN|patient\s+id|medical\s+record|health\s+id|uhid|ip\s*no\.?)\s*[:#]?\s*[\w-]+\b"
)
_CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

# FINTECH: Additional PII patterns for financial services
_BANK_ACCOUNT_PATTERN = re.compile(r"\b\d{10,16}\b")  # Bank/card account numbers
_IFSC_PATTERN = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")  # IFSC code
_PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")  # PAN (Permanent Account Number)
_GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z0-9]{1}Z[A-Z0-9]{1}\b")  # GSTIN
_POLICY_PATTERN = re.compile(r"(?i)(policy|policy\s+number|policy\s+no\.?|policyno)\s*[:#]?\s*[\w-]{6,20}")
_DEMAT_PATTERN = re.compile(r"(?i)(demat|dp\s+id|demat\s+account)\s*[:#]?\s*[\w-]{8,20}")
_FOLIO_PATTERN = re.compile(r"(?i)(folio|folio\s+number|folio\s+no\.?)\s*[:#]?\s*[\w-]{6,20}")
_LOAN_ACCOUNT_PATTERN = re.compile(r"(?i)(loan\s+account|loan\s+no\.?|loanno)\s*[:#]?\s*[\w-]{6,20}")
_OTP_PATTERN = re.compile(r"(?i)\b(otp|one.time.password|password|pin|code)\s*(?:is|are|:|#)?\s*\d{4,6}\b")
_CVV_PATTERN = re.compile(r"(?i)\b(cvv|cvc|verification|code|security)\s*(?:is|are|:|#)?\s*\d{3,4}\b")
_SWIFT_PATTERN = re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}[A-Z0-9]{3}\b")  # SWIFT code
_NEFT_PATTERN = re.compile(r"(?i)\b(neft|neft\s+ref|transaction\s+ref|txn\s+id)\s*[:#]?\s*[\w-]{10,20}\b")
_PASSPORT_PATTERN = re.compile(r"(?i)(passport|passport\s+no\.?)\s*[:#]?\s*[A-Z0-9]{6,9}")
_TRADING_ACCOUNT_PATTERN = re.compile(r"(?i)(trading\s+account|trade\s+id|client\s+id)\s*[:#]?\s*[\w-]{6,20}")

GUARDRAIL_USER_ERROR = "Transcript could not be analyzed. Please upload a valid call recording."


def get_max_transcript_chars() -> int:
    settings = get_settings()
    return getattr(settings, "guardrails_max_transcript_chars", None) or settings.sarvam_llm_max_transcript_chars


def pii_masking_enabled() -> bool:
    settings = get_settings()
    return bool(getattr(settings, "guardrails_pii_masking_enabled", True))


def safe_log_preview(text: str, *, max_len: int = 80) -> str:
    """Redact PII and truncate for log lines."""
    preview = mask_pii(text or "")[:max_len]
    if len(text or "") > max_len:
        preview += "..."
    return preview


def mask_pii(text: str) -> str:
    """Mask common PII patterns. Used for client output and safe logging."""
    if not text:
        return text

    masked = text
    masked = _PHONE_PATTERN.sub("[PHONE REDACTED]", masked)
    masked = _EMAIL_PATTERN.sub("[EMAIL REDACTED]", masked)
    masked = _SSN_PATTERN.sub("[ID REDACTED]", masked)
    masked = _AADHAAR_PATTERN.sub("[ID REDACTED]", masked)
    masked = _MEDICAL_ID_PATTERN.sub("[MEDICAL ID REDACTED]", masked)
    masked = _CREDIT_CARD_PATTERN.sub("[CARD REDACTED]", masked)
    
    # FINTECH: Mask financial services PII
    masked = _BANK_ACCOUNT_PATTERN.sub("[ACCOUNT REDACTED]", masked)
    masked = _IFSC_PATTERN.sub("[IFSC REDACTED]", masked)
    masked = _PAN_PATTERN.sub("[PAN REDACTED]", masked)
    masked = _GSTIN_PATTERN.sub("[GSTIN REDACTED]", masked)
    masked = _POLICY_PATTERN.sub("[POLICY REDACTED]", masked)
    masked = _DEMAT_PATTERN.sub("[DEMAT ACCOUNT REDACTED]", masked)
    masked = _FOLIO_PATTERN.sub("[FOLIO REDACTED]", masked)
    masked = _LOAN_ACCOUNT_PATTERN.sub("[LOAN ACCOUNT REDACTED]", masked)
    masked = _OTP_PATTERN.sub("[OTP/PASSWORD REDACTED]", masked)
    masked = _CVV_PATTERN.sub("[CVV REDACTED]", masked)
    masked = _SWIFT_PATTERN.sub("[SWIFT CODE REDACTED]", masked)
    masked = _NEFT_PATTERN.sub("[REFERENCE REDACTED]", masked)
    masked = _PASSPORT_PATTERN.sub("[PASSPORT REDACTED]", masked)
    masked = _TRADING_ACCOUNT_PATTERN.sub("[TRADING ACCOUNT REDACTED]", masked)
    
    return masked


def detect_prompt_injection(text: str) -> list[str]:
    """Return labels for suspicious injection patterns found in transcript text."""
    if not text:
        return []
    triggers: list[str] = []
    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            triggers.append(label)
    return triggers


def _neutralize_delimiters(text: str) -> str:
    """Prevent transcript content from breaking prompt delimiters."""
    return (
        text.replace(TRANSCRIPT_START, "[[TRANSCRIPT_START]]")
        .replace(TRANSCRIPT_END, "[[TRANSCRIPT_END]]")
    )


def shorten_transcript(transcript: str, *, attempt: int, max_chars: int) -> str:
    """Trim long transcripts on retry instead of requesting more output tokens."""
    text = " ".join((transcript or "").split())
    if not text:
        return ""

    if attempt <= 0:
        limit = max_chars
    else:
        limit = max(2000, max_chars // (2**attempt))

    if len(text) <= limit:
        return text

    content_budget = limit - len(TRANSCRIPT_SHORTENED_MARKER)
    if content_budget < 200:
        return text[:limit]

    head = int(content_budget * 0.65)
    tail = content_budget - head
    shortened = f"{text[:head]}{TRANSCRIPT_SHORTENED_MARKER}{text[-tail:]}"
    logger.info(
        "Guardrail shortened transcript attempt=%s from_chars=%s to_chars=%s",
        attempt + 1,
        len(text),
        len(shortened),
    )
    return shortened


def prepare_transcript_for_analysis(
    transcript: str,
    *,
    attempt: int = 0,
    max_chars: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Normalize, scan, shorten, and wrap transcript for LLM prompts.
    Returns (wrapped_transcript, metadata).
    """
    limit = max_chars if max_chars is not None else get_max_transcript_chars()
    normalized = " ".join((transcript or "").split())
    triggers = detect_prompt_injection(normalized)
    if triggers:
        logger.warning(
            "Guardrail prompt-injection patterns detected: %s (preview=%r)",
            ", ".join(triggers),
            safe_log_preview(normalized),
        )

    shortened = shorten_transcript(normalized, attempt=attempt, max_chars=limit)
    if len(shortened) < len(normalized):
        triggers = list(dict.fromkeys([*triggers, "transcript_shortened"]))

    safe_body = _neutralize_delimiters(shortened)
    wrapped = f"{TRANSCRIPT_START}\n{safe_body}\n{TRANSCRIPT_END}"
    return wrapped, {"injection_triggers": triggers, "char_count": len(shortened)}


def validate_transcript_for_analysis(transcript: str, *, max_chars: int | None = None) -> str | None:
    """Return a user-safe error message when transcript is not suitable for analysis."""
    text = (transcript or "").strip()
    if not text:
        return GUARDRAIL_USER_ERROR

    limit = max_chars if max_chars is not None else get_max_transcript_chars()
    if len(text) > limit * 2:
        logger.warning(
            "Guardrail rejected oversized transcript chars=%s limit=%s",
            len(text),
            limit,
        )
        return GUARDRAIL_USER_ERROR

    letter_count = sum(1 for c in text if c.isalpha())
    if letter_count < 3:
        logger.warning("Guardrail rejected transcript with insufficient content")
        return GUARDRAIL_USER_ERROR

    return None


def _clamp_enum(value: str, allowed: frozenset[str], default: str) -> str:
    normalized = (value or "").strip().lower().replace(" ", "_")
    return normalized if normalized in allowed else default


def sanitize_analysis_dict(data: dict) -> dict:
    """Enforce enums, strip unsafe free-form content, and mask PII in analysis fields."""
    out = dict(data)
    out["sentiment"] = _clamp_enum(str(out.get("sentiment", "")), VALID_SENTIMENTS, "neutral")
    out["resolution_status"] = _clamp_enum(
        str(out.get("resolution_status", "")),
        VALID_RESOLUTION_STATUSES,
        "unresolved",
    )

    try:
        confidence = float(out.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    out["confidence"] = min(max(confidence, 0.0), 1.0)

    for key in ("summary", "notes"):
        value = str(out.get(key) or "").strip()
        out[key] = mask_pii(value) if pii_masking_enabled() else value

    for list_key, alt_key in (("key_issues", "issues"), ("action_items", "actions")):
        items = out.get(list_key)
        if items is None:
            items = out.get(alt_key)
        if not isinstance(items, list):
            items = []
        cleaned = []
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if not text:
                continue
            cleaned.append(mask_pii(text) if pii_masking_enabled() else text)
        out[list_key] = cleaned
        if alt_key in out:
            out[alt_key] = cleaned

    return out


def sanitize_provider_result_for_client(result: ProviderResult) -> ProviderResult:
    """Strip internal metadata, mask PII, and hide raw provider payloads from clients."""
    data = result.model_dump()
    data["stt_language_code"] = None
    data["detected_script"] = None
    data["language_mismatch_warning"] = None
    data["whisper_detected_language"] = None
    data["raw_llm_response"] = None
    data["raw_stt_response"] = None

    if pii_masking_enabled() and data.get("transcript"):
        data["transcript"] = mask_pii(str(data["transcript"]))

    analysis = data.get("analysis")
    if analysis and isinstance(analysis, dict):
        sanitized = sanitize_analysis_dict(analysis)
        data["analysis"] = enrich_analysis(
            AnalysisResult(
                sentiment=sanitized["sentiment"],
                key_issues=sanitized.get("key_issues") or [],
                summary=sanitized.get("summary") or "",
                action_items=sanitized.get("action_items") or [],
                resolution_status=sanitized["resolution_status"],
                confidence=sanitized["confidence"],
                notes=sanitized.get("notes") or "",
            )
        )

    if data.get("error"):
        data["error"] = _sanitize_client_error(str(data["error"]))

    return ProviderResult(**data)


def _sanitize_client_error(error: str) -> str:
    """Return clean, non-leaky error text for the UI."""
    lowered = error.lower()
    if "max_tokens" in lowered and "exceed" in lowered:
        return "Analysis service limit reached. Please try again with a shorter recording."
    if "validation" in lowered or "unsupported format" in lowered:
        return error
    if "english translation failed" in lowered:
        return error
    if "api key" in lowered or "not configured" in lowered:
        return "Analysis service is temporarily unavailable."
    if "timed out" in lowered or "timeout" in lowered:
        return "Analysis timed out. Please try again."
    if "rate limit" in lowered or "429" in lowered:
        return "Analysis service is busy. Please try again shortly."
    if "json" in lowered or "schema" in lowered or "parse" in lowered:
        return "Analysis could not be completed. Please try again."
    return error if len(error) <= 200 else error[:200] + "..."
