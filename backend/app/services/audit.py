"""Job audit trail — structured logs + durable DB events."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import obs_logger
from app.models.db_models import JobAuditEvent

logger = logging.getLogger(__name__)

# Events that must never include transcript or PII in metadata.
_SAFE_META_KEYS = frozenset(
    {
        "filename",
        "extension",
        "size_bytes",
        "mime_type",
        "duration_seconds",
        "solution_id",
        "status",
        "error_type",
        "retry_count",
        "pending_providers",
        "completed_count",
        "failed_count",
        "runtime_seconds",
        "sentiment",
        "confidence",
    }
)


def _sanitize_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    return {k: v for k, v in meta.items() if k in _SAFE_META_KEYS}


async def record_audit_event(
    db: AsyncSession | None,
    *,
    job_id: str,
    event_type: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    level: str = "info",
) -> None:
    safe_meta = _sanitize_meta(metadata)
    log_fields = {
        "job_id": job_id,
        "event_type": event_type,
        "message": message,
        "event_level": level,
        **safe_meta,
    }
    log_fn = {
        "error": obs_logger.error,
        "warning": obs_logger.warning,
        "debug": obs_logger.debug,
    }.get(level, obs_logger.info)
    log_fn("job_audit", **log_fields)

    if db is None:
        return

    event = JobAuditEvent(
        job_id=job_id,
        event_type=event_type,
        message=message[:2000],
        metadata_json=json.dumps(safe_meta) if safe_meta else None,
        level=level,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    try:
        await db.commit()
    except Exception:
        logger.exception("Failed to persist audit event job_id=%s type=%s", job_id, event_type)
        await db.rollback()
