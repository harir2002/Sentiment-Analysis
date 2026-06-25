from app.core.config import PLACEHOLDER_KEYS, Settings


def test_placeholder_keys_detected():
    settings = Settings(sarvam_api_key="your_sarvam_api_key_here")
    assert not settings.has_sarvam_key()


def test_real_key_detected():
    settings = Settings(sarvam_api_key="sk_live_test_key_12345")
    assert settings.has_sarvam_key()


def test_require_sarvam_key_raises_for_placeholder():
    settings = Settings(sarvam_api_key="")
    try:
        settings.require_sarvam_key()
        raised = False
    except ValueError as e:
        raised = True
        assert "SARVAM_API_KEY" in str(e)
    assert raised


def test_openrouter_default_model():
    default = Settings.model_fields["openrouter_llm_model"].default
    assert default == "google/gemma-4-26b-a4b-it"


def test_cors_origin_list_parsed():
    settings = Settings(cors_origins="http://a.com, http://b.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


def test_max_upload_bytes():
    settings = Settings(max_upload_size_mb=25)
    assert settings.max_upload_bytes == 25 * 1024 * 1024


def test_placeholder_keys_set():
    assert "changeme" in PLACEHOLDER_KEYS
    assert "your_openrouter_api_key_here" in PLACEHOLDER_KEYS
