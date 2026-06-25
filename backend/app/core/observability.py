"""In-process metrics and structured observability helpers."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class StructuredLogger:
    """JSON-friendly structured log lines when log_format=json."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    @staticmethod
    def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
        """Rename reserved keys that collide with _emit() parameters."""
        if "level" not in fields:
            return fields
        sanitized = dict(fields)
        sanitized["event_level"] = sanitized.pop("level")
        return sanitized

    def _emit(self, log_level: int, event: str, **fields: Any) -> None:
        fields = self._sanitize_fields(fields)
        rid = request_id_ctx.get()
        if rid:
            fields["request_id"] = rid
        payload = {"event": event, **fields}
        self._logger.log(log_level, json.dumps(payload, default=str))

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, **fields)


@dataclass
class MetricsCollector:
    """Thread-safe counters for ops dashboards and /metrics."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    requests_total: int = 0
    requests_5xx: int = 0
    requests_4xx: int = 0
    slow_requests: int = 0
    jobs_started: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    uploads_accepted: int = 0
    uploads_rejected: int = 0
    provider_errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latency_ms_sum: float = 0.0
    latency_ms_count: int = 0
    pipeline_latency_ms_sum: float = 0.0
    pipeline_latency_ms_count: int = 0
    started_at: float = field(default_factory=time.time)

    def record_request(self, *, status_code: int, latency_ms: float, slow_threshold_ms: float) -> None:
        with self._lock:
            self.requests_total += 1
            self.latency_ms_sum += latency_ms
            self.latency_ms_count += 1
            if status_code >= 500:
                self.requests_5xx += 1
            elif status_code >= 400:
                self.requests_4xx += 1
            if latency_ms >= slow_threshold_ms:
                self.slow_requests += 1

    def record_job_started(self) -> None:
        with self._lock:
            self.jobs_started += 1

    def record_job_finished(self, *, success: bool, runtime_seconds: float | None = None) -> None:
        with self._lock:
            if success:
                self.jobs_completed += 1
            else:
                self.jobs_failed += 1
            if runtime_seconds is not None:
                self.pipeline_latency_ms_sum += runtime_seconds * 1000
                self.pipeline_latency_ms_count += 1

    def record_upload(self, *, accepted: bool) -> None:
        with self._lock:
            if accepted:
                self.uploads_accepted += 1
            else:
                self.uploads_rejected += 1

    def record_provider_error(self, provider: str) -> None:
        with self._lock:
            self.provider_errors[provider] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_latency = (
                self.latency_ms_sum / self.latency_ms_count if self.latency_ms_count else 0.0
            )
            avg_pipeline = (
                self.pipeline_latency_ms_sum / self.pipeline_latency_ms_count
                if self.pipeline_latency_ms_count
                else 0.0
            )
            error_rate = (
                self.requests_5xx / self.requests_total if self.requests_total else 0.0
            )
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests": {
                    "total": self.requests_total,
                    "4xx": self.requests_4xx,
                    "5xx": self.requests_5xx,
                    "slow": self.slow_requests,
                    "avg_latency_ms": round(avg_latency, 1),
                    "error_rate": round(error_rate, 4),
                },
                "jobs": {
                    "started": self.jobs_started,
                    "completed": self.jobs_completed,
                    "failed": self.jobs_failed,
                    "avg_pipeline_ms": round(avg_pipeline, 1),
                },
                "uploads": {
                    "accepted": self.uploads_accepted,
                    "rejected": self.uploads_rejected,
                },
                "provider_errors": dict(self.provider_errors),
            }


metrics = MetricsCollector()
obs_logger = StructuredLogger("app.observability")
