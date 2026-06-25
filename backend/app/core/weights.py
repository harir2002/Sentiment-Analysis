import yaml
from pathlib import Path
from functools import lru_cache
from app.core.config import get_settings


@lru_cache
def load_weights_config() -> dict:
    settings = get_settings()
    config_path = Path(settings.weights_config_path)
    if not config_path.is_absolute():
        config_path = settings.backend_root / config_path

    if not config_path.exists():
        return _default_weights()

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or _default_weights()


def _default_weights() -> dict:
    return {
        # FINTECH: Updated weights prioritizing compliance and analysis quality
        "weights": {
            "stt_quality": 0.15,  # Reduced - accuracy less critical than compliance
            "llm_analysis_quality": 0.25,  # Increased - analysis quality important
            "latency": 0.10,  # Reduced - speed less critical in fintech
            "cost": 0.10,  # Same - cost always matters
            "indian_language_suitability": 0.15,  # Same - important for India
            "compliance_control": 0.25,  # Significantly increased - critical for regulated environment
        },
        "cost_per_minute": {
            "sarvam_stt": 0.008,
            "sarvam_llm": 0.003,
            "groq_whisper": 0.005,
            "openrouter_gemma": 0.003,
        },
        "latency_benchmark_seconds": 30,
        "indian_language_scores": {
            "sarvam_stt": 0.95,  # Excellent for Indian languages
            "sarvam_llm": 0.95,  # Excellent for Indian language analysis
            "groq_whisper": 0.70,  # Good English, lower for Indian languages
            "openrouter_gemma": 0.70,  # Good English, lower for Indian languages
        },
        # FINTECH: Upgraded compliance scores for regulated environment
        "compliance_scores": {
            "sarvam_stt": 0.95,  # Upgraded - better for financial services
            "sarvam_llm": 0.95,  # Upgraded - better at capturing compliance data
            "groq_whisper": 0.70,  # Standard - generic English transcription
            "openrouter_gemma": 0.70,  # Standard - generic English LLM
        },
        # FINTECH: New compliance-specific scoring criteria
        "compliance_data_capture_weights": {
            "kyc_status_captured": 0.15,  # Critical for compliance
            "regulatory_mentions_detected": 0.15,  # Critical for compliance
            "fraud_indicators_identified": 0.20,  # Critical for risk management
            "product_type_extracted": 0.15,  # Important for routing
            "transaction_amount_captured": 0.15,  # Important for high-value flagging
            "callback_requirement_identified": 0.10,  # Important for follow-up
            "escalation_level_correct": 0.10,  # Important for routing
        }
    }
