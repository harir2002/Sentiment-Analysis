from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"

# Load .env before Settings is first instantiated (database.py calls get_settings at import time)
load_dotenv(_ENV_FILE, override=True)
load_dotenv(_BACKEND_ROOT.parent / ".env", override=True)

PLACEHOLDER_KEYS = {
    "",
    "your_sarvam_api_key_here",
    "your_groq_api_key_here",
    "your_openrouter_api_key_here",
    "changeme",
}

# Sarvam LLM max_tokens caps by subscription tier (sarvam-30b).
# Reduced to 1000 tokens to force concise JSON output and prevent truncation
# (Lower limit = faster response, concise JSON = no finish_reason=length errors)
SARVAM_LLM_TIER_MAX_TOKENS: dict[str, int] = {
    "starter": 1000,
    "growth": 2000,
    "enterprise": 3000,
}
SARVAM_LLM_DEFAULT_MAX_TOKENS = 1000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    sql_echo: bool = False
    access_log: bool = True
    api_max_retries: int = 3
    api_retry_base_seconds: float = 1.0
    admin_username: str = "admin"
    admin_password: str = "changeme"

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    upload_dir: str = "./data/uploads"
    max_upload_size_mb: int = 25
    min_sample_rate_hz: int = 8000
    max_sample_rate_hz: int = 48000
    cleanup_audio_after_job: bool = True

    sarvam_api_key: str = ""
    sarvam_stt_url: str = "https://api.sarvam.ai/speech-to-text"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_stt_mode: str = "transcribe"
    sarvam_stt_language: str = "unknown"
    sarvam_rest_max_seconds: float = 30.0
    sarvam_batch_max_wait_seconds: float = 120.0
    sarvam_batch_poll_interval: float = 5.0
    sarvam_batch_absolute_max_seconds: float = 3600.0
    sarvam_batch_blocking_poll_seconds: float = 0.0
    sarvam_chunk_stt_enabled: bool = True
    sarvam_chunk_seconds: float = 25.0
    sarvam_llm_url: str = "https://api.sarvam.ai/v1/chat/completions"
    sarvam_llm_model: str = "sarvam-30b"
    sarvam_llm_plan_tier: str = "starter"
    sarvam_llm_max_tokens: int = SARVAM_LLM_DEFAULT_MAX_TOKENS
    sarvam_llm_content_retries: int = 3
    sarvam_llm_max_transcript_chars: int = 12000

    guardrails_max_transcript_chars: int = 12000
    guardrails_pii_masking_enabled: bool = True

    log_format: str = "text"
    expose_error_details: bool = False
    metrics_enabled: bool = True
    slow_request_threshold_ms: float = 5000.0
    request_id_header: str = "X-Request-ID"

    @property
    def is_production(self) -> bool:
        return (self.app_env or "").strip().lower() in {"production", "prod"}

    @property
    def show_error_details(self) -> bool:
        if self.is_production:
            return False
        return self.expose_error_details

    groq_api_key: str = ""
    groq_stt_model: str = "whisper-large-v3"
    groq_stt_url: str = "https://api.groq.com/openai/v1/audio/transcriptions"

    @property
    def groq_stt_translate_url(self) -> str:
        if self.groq_stt_url.rstrip("/").endswith("/transcriptions"):
            return self.groq_stt_url.rstrip("/").replace("/transcriptions", "/translations")
        return "https://api.groq.com/openai/v1/audio/translations"

    openrouter_api_key: str = ""
    openrouter_llm_model: str = "google/gemma-4-26b-a4b-it"
    openrouter_llm_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_app_name: str = "Call Analytics Lab"
    
    # PRODUCTION: Choose which solution to run
    active_solution: str = "sarvam_stt_sarvam_llm"  # or any SolutionOption value

    # Odoo CRM Integration
    odoo_server_url: str = ""  # e.g., https://your-instance.odoo.com
    odoo_db_name: str = ""  # Database name
    odoo_username: str = ""  # Email or username
    odoo_password: str = ""  # Password or API token
    odoo_api_key: str = ""  # Optional API key if using external API
    odoo_enabled: bool = False  # Set to true to enable CRM sync

    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    weights_config_path: str = "config/weights.yaml"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sarvam_llm_token_limit(self) -> int:
        """Effective max_tokens cap for the configured Sarvam plan tier."""
        tier = (self.sarvam_llm_plan_tier or "starter").strip().lower()
        tier_cap = SARVAM_LLM_TIER_MAX_TOKENS.get(tier, SARVAM_LLM_DEFAULT_MAX_TOKENS)
        requested = self.sarvam_llm_max_tokens or SARVAM_LLM_DEFAULT_MAX_TOKENS
        return max(256, min(requested, tier_cap))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def backend_root(self) -> Path:
        return _BACKEND_ROOT

    def has_sarvam_key(self) -> bool:
        return self.sarvam_api_key.strip() not in PLACEHOLDER_KEYS

    def has_groq_key(self) -> bool:
        return self.groq_api_key.strip() not in PLACEHOLDER_KEYS

    def has_openrouter_key(self) -> bool:
        return self.openrouter_api_key.strip() not in PLACEHOLDER_KEYS

    def require_sarvam_key(self) -> str:
        key = self.sarvam_api_key.strip()
        if key in PLACEHOLDER_KEYS:
            raise ValueError(
                "SARVAM_API_KEY is missing or not configured. "
                "Set a valid key in your .env file."
            )
        return key

    def require_groq_key(self) -> str:
        key = self.groq_api_key.strip()
        if key in PLACEHOLDER_KEYS:
            raise ValueError(
                "GROQ_API_KEY is missing or not configured. "
                "Set a valid key in your .env file (used for Whisper STT)."
            )
        return key

    def require_openrouter_key(self) -> str:
        key = self.openrouter_api_key.strip()
        if key in PLACEHOLDER_KEYS:
            raise ValueError(
                "OPENROUTER_API_KEY is missing or not configured. "
                "Set a valid key in your .env file (used for Gemma 4 26B LLM via OpenRouter)."
            )
        return key


def get_settings() -> Settings:
    # Re-load on each access so .env edits apply without a full server restart
    load_dotenv(_ENV_FILE, override=True)
    load_dotenv(_BACKEND_ROOT.parent / ".env", override=True)
    return Settings()
