"""English-only STT output validation and client-facing sanitization."""
from __future__ import annotations

import logging
import re

from app.models.schemas import ProviderResult
from app.services.guardrails import safe_log_preview, sanitize_provider_result_for_client
from app.services.stt_language import analyze_transcript_language

logger = logging.getLogger(__name__)

ENGLISH_TRANSLATION_FAILED = (
    "English translation failed. Please try again with a clearer audio recording."
)

# Minimum share of Latin letters for a transcript to be treated as English output.
_MIN_LATIN_RATIO = 0.55
_MIN_LETTERS = 6

_INDIC_SCRIPTS = frozenset(
    {
        "tamil",
        "telugu",
        "kannada",
        "malayalam",
        "devanagari",
        "bengali",
        "gujarati",
        "gurmukhi",
    }
)


def sarvam_mode_for_english_output(model: str, configured_mode: str) -> str:
    """Use Sarvam translate mode when supported (saaras) to emit English text."""
    if "saaras" in (model or "").lower():
        return "translate"
    return (configured_mode or "transcribe").strip() or "transcribe"


def is_predominantly_english(text: str) -> bool:
    if not text or not text.strip():
        return False

    letters = [c for c in text if c.isalpha()]
    if len(letters) < _MIN_LETTERS:
        return False

    latin = sum(1 for c in letters if c.isascii())
    if latin / len(letters) < _MIN_LATIN_RATIO:
        return False

    analysis = analyze_transcript_language(text)
    dominant = analysis.get("dominant_script")
    if dominant in _INDIC_SCRIPTS:
        counts = analysis.get("script_counts") or {}
        indic_total = sum(counts.get(s, 0) for s in _INDIC_SCRIPTS)
        latin_count = counts.get("latin", 0)
        if indic_total > latin_count and indic_total >= 3:
            return False

    return True


def validate_english_transcript(text: str) -> str | None:
    """Return an error message when transcript is not usable English output."""
    if not text or not text.strip():
        return ENGLISH_TRANSLATION_FAILED
    if is_predominantly_english(text):
        return None
    logger.warning(
        "Transcript failed English validation (length=%s, preview=%r)",
        len(text),
        safe_log_preview(text),
    )
    return ENGLISH_TRANSLATION_FAILED


def normalize_english_transcript(text: str) -> str:
    """Light cleanup before sentiment analysis."""
    cleaned = " ".join((text or "").split())
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    return cleaned.strip()


__all__ = [
    "ENGLISH_TRANSLATION_FAILED",
    "is_predominantly_english",
    "normalize_english_transcript",
    "sanitize_provider_result_for_client",
    "sarvam_mode_for_english_output",
    "validate_english_transcript",
]
