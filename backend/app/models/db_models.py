from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ComparisonJob(Base):
    __tablename__ = "comparison_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    audio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    call_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stt_language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Single result for production
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Old: kept for backward compatibility
    ranking: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class JobAuditEvent(Base):
    __tablename__ = "job_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
