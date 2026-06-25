import pytest

from app.core.config import Settings


def test_production_hides_error_details():
    settings = Settings(app_env="production", expose_error_details=True)
    assert settings.show_error_details is False


def test_development_can_expose_error_details():
    settings = Settings(app_env="development", expose_error_details=True)
    assert settings.show_error_details is True


def test_sarvam_token_limit_starter():
    settings = Settings(
        sarvam_llm_plan_tier="starter",
        sarvam_llm_max_tokens=8192,
    )
    assert settings.sarvam_llm_token_limit == 4096
