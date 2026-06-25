import json
import logging

import pytest

from app.core.observability import MetricsCollector, StructuredLogger
from app.services.audit import record_audit_event


def test_metrics_record_request():
    m = MetricsCollector()
    m.record_request(status_code=200, latency_ms=100, slow_threshold_ms=5000)
    m.record_request(status_code=500, latency_ms=6000, slow_threshold_ms=5000)
    snap = m.snapshot()
    assert snap["requests"]["total"] == 2
    assert snap["requests"]["5xx"] == 1
    assert snap["requests"]["slow"] == 1


def test_metrics_job_lifecycle():
    m = MetricsCollector()
    m.record_job_started()
    m.record_job_finished(success=True, runtime_seconds=12.5)
    m.record_job_finished(success=False)
    snap = m.snapshot()
    assert snap["jobs"]["started"] == 1
    assert snap["jobs"]["completed"] == 1
    assert snap["jobs"]["failed"] == 1


def test_metrics_provider_errors():
    m = MetricsCollector()
    m.record_provider_error("sarvam_stt_sarvam_llm")
    m.record_provider_error("sarvam_stt_sarvam_llm")
    assert m.snapshot()["provider_errors"]["sarvam_stt_sarvam_llm"] == 2


def test_structured_logger_renames_conflicting_level_field(caplog):
    caplog.set_level(logging.INFO, logger="test.structured")
    logger = StructuredLogger("test.structured")

    logger.info("test_event", level="high")

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "test_event"
    assert payload["event_level"] == "high"
    assert "level" not in payload


@pytest.mark.asyncio
async def test_record_audit_event_error_level_uses_error_severity(caplog):
    caplog.set_level(logging.ERROR, logger="app.observability")

    await record_audit_event(
        None,
        job_id="job-1",
        event_type="job_failed",
        message="Job failed during processing",
        level="error",
        metadata={"error_type": "ValueError"},
    )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "job_audit"
    assert payload["event_level"] == "error"
    assert payload["error_type"] == "ValueError"
