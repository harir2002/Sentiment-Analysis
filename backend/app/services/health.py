"""Liveness, readiness, and dependency health probes."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.core.observability import metrics

logger = logging.getLogger(__name__)


async def check_database() -> tuple[bool, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False, "unavailable"


def check_upload_directory() -> tuple[bool, str]:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        probe = upload_dir / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, "writable"
    except Exception as exc:
        logger.warning("Upload directory check failed: %s", exc)
        return False, "not_writable"


def check_providers() -> dict[str, bool]:
    settings = get_settings()
    return {
        "sarvam": settings.has_sarvam_key(),
        "groq": settings.has_groq_key(),
        "openrouter": settings.has_openrouter_key(),
    }


async def readiness_report() -> dict:
    settings = get_settings()
    db_ok, db_status = await check_database()
    upload_ok, upload_status = check_upload_directory()
    providers = check_providers()
    any_provider = any(providers.values())

    checks = {
        "database": db_status,
        "upload_dir": upload_status,
        "providers": providers,
    }
    ready = db_ok and upload_ok and any_provider

    return {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "app_env": settings.app_env,
        "checks": checks,
        "metrics": metrics.snapshot() if settings.metrics_enabled else None,
    }


async def health_report() -> dict:
    settings = get_settings()
    db_ok, db_status = await check_database()
    upload_ok, upload_status = check_upload_directory()
    providers = check_providers()

    degraded = not db_ok or not upload_ok or not any(providers.values())
    return {
        "status": "degraded" if degraded else "ok",
        "database": db_status if db_ok else "error",
        "upload_dir": upload_status if upload_ok else "error",
        "version": "1.0.0",
        "app_env": settings.app_env,
        "providers": providers,
        "models": {
            "sarvam_stt": settings.sarvam_stt_model,
            "sarvam_llm": settings.sarvam_llm_model,
            "groq_stt": settings.groq_stt_model,
            "openrouter_llm": settings.openrouter_llm_model,
        },
        "limits": {
            "max_upload_mb": settings.max_upload_size_mb,
            "max_transcript_chars": settings.guardrails_max_transcript_chars,
            "sarvam_llm_max_tokens": settings.sarvam_llm_token_limit,
        },
    }
