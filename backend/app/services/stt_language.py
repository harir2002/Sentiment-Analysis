"""STT language auto-detection, normalization, and transcript validation."""
from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger(__name__)

AUTO_DETECT_CODE = "auto"
SARVAM_AUTO_DETECT = "unknown"

# Internal candidate list for Indian languages (not exposed in UI).
SUPPORTED_LANGUAGES: dict[str, str] = {
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "hi-IN": "Hindi",
    "en-IN": "English",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
}

WHISPER_ISO_TO_BCP47: dict[str, str] = {
    "ta": "ta-IN",
    "te": "te-IN",
    "hi": "hi-IN",
    "en": "en-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "bn": "bn-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
}

WHISPER_LANGUAGE_PROMPTS: dict[str, str] = {
    "ta": "வணக்கம். இது தமிழ் மொழியில் பேசப்பட்ட குரல் பதிவு.",
    "te": "నమస్కారం. ఇది తెలుగు భాషలో మాట్లాడిన ఆడియో రికార్డింగ్.",
    "hi": "नमस्ते। यह हिंदी भाषा में बोला गया ऑडियो रिकॉर्डिंग है।",
    "en": "Hello. This is an English language voice recording.",
}

_SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gujarati": (0x0A80, 0x0AFF),
    "gurmukhi": (0x0A00, 0x0A7F),
}

_LANGUAGE_TO_SCRIPT: dict[str, str] = {
    "ta": "tamil",
    "te": "telugu",
    "kn": "kannada",
    "ml": "malayalam",
    "hi": "devanagari",
    "mr": "devanagari",
    "bn": "bengali",
    "gu": "gujarati",
    "pa": "gurmukhi",
    "en": "latin",
}

_SCRIPT_TO_BCP47: dict[str, str] = {
    "tamil": "ta-IN",
    "telugu": "te-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "devanagari": "hi-IN",
    "bengali": "bn-IN",
    "gujarati": "gu-IN",
    "gurmukhi": "pa-IN",
    "latin": "en-IN",
}


def is_auto_detect(language_code: str | None) -> bool:
    if language_code is None:
        return True
    lowered = str(language_code).strip().lower()
    return lowered in {"", "auto", "unknown", "auto-detect", "auto_detect"}


def normalize_language_code(code: str | None) -> str:
    if is_auto_detect(code):
        return AUTO_DETECT_CODE

    lowered = str(code).strip().lower()
    for key in SUPPORTED_LANGUAGES:
        if key.lower() == lowered:
            return key

    if len(lowered) == 2:
        candidate = f"{lowered}-in"
        for key in SUPPORTED_LANGUAGES:
            if key.lower() == candidate:
                return key
        mapped = WHISPER_ISO_TO_BCP47.get(lowered)
        if mapped:
            return mapped

    raise ValueError(
        f"Unsupported language code '{code}'. "
        f"Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
    )


def cache_key_for_language(language_code: str | None) -> str:
    if is_auto_detect(language_code):
        return AUTO_DETECT_CODE
    return normalize_language_code(language_code)


def sarvam_api_language_code(language_code: str | None) -> str:
    """Sarvam uses 'unknown' to enable automatic language detection."""
    if is_auto_detect(language_code):
        return SARVAM_AUTO_DETECT
    return normalize_language_code(language_code)


def whisper_language_code(language_code: str) -> str:
    resolved = normalize_language_code(language_code)
    if resolved == AUTO_DETECT_CODE:
        raise ValueError("Whisper language code requires a resolved language, not auto-detect")
    return resolved.split("-")[0].lower()


def whisper_initial_prompt(language_code: str) -> str | None:
    if is_auto_detect(language_code):
        return None
    base = whisper_language_code(normalize_language_code(language_code))
    return WHISPER_LANGUAGE_PROMPTS.get(base)


def display_language(language_code: str | None) -> str:
    if not language_code or is_auto_detect(language_code):
        return "Auto-detected"
    try:
        resolved = normalize_language_code(language_code)
    except ValueError:
        return str(language_code)
    if resolved == AUTO_DETECT_CODE:
        return "Auto-detected"
    return SUPPORTED_LANGUAGES.get(resolved, resolved)


def extract_sarvam_detected_language(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    raw = data.get("language_code") or data.get("detected_language")
    if not raw or is_auto_detect(str(raw)):
        return None
    try:
        return normalize_language_code(str(raw))
    except ValueError:
        iso = str(raw).split("-")[0].lower()
        return WHISPER_ISO_TO_BCP47.get(iso)


def _count_script_chars(text: str) -> dict[str, int]:
    counts: dict[str, int] = {name: 0 for name in _SCRIPT_RANGES}
    latin = 0

    for char in text:
        if char.isspace() or unicodedata.category(char).startswith("P"):
            continue
        cp = ord(char)
        matched = False
        for script, (start, end) in _SCRIPT_RANGES.items():
            if start <= cp <= end:
                counts[script] += 1
                matched = True
                break
        if not matched and ("LATIN" in unicodedata.name(char, "") or cp < 128):
            latin += 1

    counts["latin"] = latin
    return counts


def detect_dominant_script(transcript: str) -> str | None:
    if not transcript or not transcript.strip():
        return None

    counts = _count_script_chars(transcript)
    best_script = max(
        (k for k in counts if k != "latin"),
        key=lambda k: counts[k],
        default=None,
    )
    if not best_script or counts[best_script] < 3:
        if counts.get("latin", 0) >= 5:
            return "latin"
        return None
    return best_script


def analyze_transcript_language(transcript: str) -> dict:
    counts = _count_script_chars(transcript or "")
    dominant = detect_dominant_script(transcript or "")
    indic_total = sum(counts.get(s, 0) for s in _SCRIPT_RANGES)
    return {
        "dominant_script": dominant,
        "script_counts": counts,
        "indic_char_total": indic_total,
    }


def infer_detected_language_code(
    *,
    whisper_detected: str | None = None,
    sarvam_detected: str | None = None,
    transcript: str | None = None,
) -> str | None:
    """Infer BCP-47 language from provider hints and transcript script."""
    if sarvam_detected and not is_auto_detect(sarvam_detected):
        try:
            return normalize_language_code(sarvam_detected)
        except ValueError:
            pass

    if whisper_detected:
        iso = whisper_detected.strip().lower()
        if iso in WHISPER_ISO_TO_BCP47:
            return WHISPER_ISO_TO_BCP47[iso]

    analysis = analyze_transcript_language(transcript or "")
    script = analysis.get("dominant_script")
    if script and script in _SCRIPT_TO_BCP47:
        return _SCRIPT_TO_BCP47[script]

    return None


def expected_script_for_language(language_code: str) -> str | None:
    if is_auto_detect(language_code):
        return None
    base = whisper_language_code(normalize_language_code(language_code))
    return _LANGUAGE_TO_SCRIPT.get(base)


def is_transcript_language_mismatch(language_code: str, transcript: str) -> bool:
    if is_auto_detect(language_code) or not transcript or not transcript.strip():
        return False

    expected = expected_script_for_language(language_code)
    if not expected or expected == "latin":
        return False

    dominant = detect_dominant_script(transcript)
    if not dominant or dominant == expected:
        return False

    counts = _count_script_chars(transcript)
    dominant_count = counts.get(dominant, 0)
    expected_count = counts.get(expected, 0)
    return dominant_count >= 3 and dominant_count > expected_count


def is_low_confidence_detection(
    *,
    transcript: str,
    whisper_detected: str | None = None,
    sarvam_detected: str | None = None,
    inferred_language: str | None = None,
) -> bool:
    """Flag uncertain auto-detection for internal retry (never shown as user action)."""
    if not transcript or len(transcript.strip()) < 8:
        return True

    analysis = analyze_transcript_language(transcript)
    if analysis["indic_char_total"] < 3 and analysis["script_counts"].get("latin", 0) < 5:
        return True

    if not inferred_language:
        return True

    if whisper_detected and inferred_language:
        expected_iso = whisper_language_code(inferred_language)
        if whisper_detected.lower() != expected_iso:
            return True

    if sarvam_detected and inferred_language:
        try:
            if normalize_language_code(sarvam_detected) != normalize_language_code(inferred_language):
                return True
        except ValueError:
            return True

    if is_transcript_language_mismatch(inferred_language, transcript):
        return True

    return False


def log_stt_language_event(
    *,
    provider: str,
    audio_path: str,
    mode: str,
    transcript: str | None = None,
    whisper_detected_language: str | None = None,
    sarvam_detected_language: str | None = None,
    inferred_language: str | None = None,
    phase: str = "complete",
    low_confidence: bool = False,
) -> dict:
    analysis = analyze_transcript_language(transcript or "")
    detected_script = analysis["dominant_script"]

    logger.info(
        "STT language [%s] provider=%s mode=%s whisper_detected=%s sarvam_detected=%s "
        "inferred=%s script=%s low_confidence=%s audio=%s",
        phase,
        provider,
        mode,
        whisper_detected_language or "n/a",
        sarvam_detected_language or "n/a",
        inferred_language or "unknown",
        detected_script or "unknown",
        low_confidence,
        audio_path,
    )

    return {
        "mode": mode,
        "inferred_language": inferred_language,
        "detected_script": detected_script,
        "whisper_detected_language": whisper_detected_language,
        "sarvam_detected_language": sarvam_detected_language,
        "low_confidence": low_confidence,
        "script_counts": analysis["script_counts"],
    }


def consensus_detected_language(codes: list[str | None]) -> str | None:
    valid = [c for c in codes if c and not is_auto_detect(c)]
    if not valid:
        return None
    return max(set(valid), key=valid.count)
