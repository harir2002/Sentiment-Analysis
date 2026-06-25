from app.services.stt_language import (
    AUTO_DETECT_CODE,
    SARVAM_AUTO_DETECT,
    is_auto_detect,
    normalize_language_code,
    sarvam_api_language_code,
    infer_detected_language_code,
    is_low_confidence_detection,
    whisper_language_code,
    whisper_initial_prompt,
)


def test_auto_detect_mode():
    assert is_auto_detect(None) is True
    assert is_auto_detect("auto") is True
    assert is_auto_detect("unknown") is True
    assert sarvam_api_language_code(None) == SARVAM_AUTO_DETECT
    assert normalize_language_code("auto") == AUTO_DETECT_CODE


def test_normalize_tamil_code():
    assert normalize_language_code("ta-IN") == "ta-IN"
    assert normalize_language_code("ta") == "ta-IN"


def test_whisper_maps_tamil():
    assert whisper_language_code("ta-IN") == "ta"


def test_infer_from_whisper_iso():
    assert infer_detected_language_code(whisper_detected="ta", transcript="வணக்கம்") == "ta-IN"
    assert infer_detected_language_code(whisper_detected="te", transcript="హలో") == "te-IN"


def test_infer_from_script():
    tamil_text = "வணக்கம் இது தமிழ் உரை"
    telugu_text = "హలో ఇది తెలుగు టెక్స్ట్"
    assert infer_detected_language_code(transcript=tamil_text) == "ta-IN"
    assert infer_detected_language_code(transcript=telugu_text) == "te-IN"


def test_low_confidence_on_empty():
    assert is_low_confidence_detection(transcript="", inferred_language=None) is True


def test_whisper_prompt_none_for_auto():
    assert whisper_initial_prompt("auto") is None
