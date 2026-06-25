import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.sarvam_stt_batch import (
    _ensure_job_handle,
    build_batch_job_parameters,
    resume_batch_job,
    submit_batch_job,
)


def test_build_batch_job_parameters_includes_mode_for_saaras():
    settings = MagicMock()
    settings.sarvam_stt_model = "saaras:v3"
    settings.sarvam_stt_language = "unknown"
    settings.sarvam_stt_mode = "transcribe"

    params = build_batch_job_parameters(settings, language_code=None)

    assert params["model"] == "saaras:v3"
    assert params["language_code"] == "unknown"
    assert params["with_diarization"] is False
    assert params["mode"] == "translate"


def test_build_batch_job_parameters_omits_mode_for_saarika():
    settings = MagicMock()
    settings.sarvam_stt_model = "saarika:v2.5"
    settings.sarvam_stt_language = "hi-IN"
    settings.sarvam_stt_mode = "transcribe"

    params = build_batch_job_parameters(settings)

    assert params["model"] == "saarika:v2.5"
    assert "mode" not in params


def test_ensure_job_handle_rejects_coroutine():
    async def fake_coro():
        return None

    coro = fake_coro()
    with pytest.raises(TypeError, match="unawaited coroutine"):
        _ensure_job_handle(coro, context="test")
    coro.close()


def test_ensure_job_handle_accepts_job_with_get_status():
    job = MagicMock()
    job.job_id = "job-123"
    job.get_status = AsyncMock()
    assert _ensure_job_handle(job, context="test") is job


@pytest.mark.asyncio
async def test_resume_batch_job_awaits_get_job():
    mock_job = MagicMock()
    mock_job.job_id = "batch-abc"
    mock_job.get_status = AsyncMock()

    mock_stt_client = MagicMock()
    mock_stt_client.get_job = AsyncMock(return_value=mock_job)

    mock_client = MagicMock()
    mock_client.speech_to_text_job = mock_stt_client

    with patch("app.providers.sarvam_stt_batch.AsyncSarvamAI", return_value=mock_client):
        job = await resume_batch_job("test-key", "batch-abc")

    mock_stt_client.get_job.assert_awaited_once_with("batch-abc")
    assert job is mock_job
    assert not inspect.iscoroutine(job)


@pytest.mark.asyncio
async def test_submit_batch_job_uses_initialise_not_create_job():
    mock_job = MagicMock()
    mock_job.job_id = "batch-new"
    mock_job.get_status = AsyncMock()
    mock_job.upload_files = AsyncMock()
    mock_job.start = AsyncMock()

    mock_init_response = MagicMock()
    mock_init_response.job_id = "batch-new"

    mock_stt_client = MagicMock()
    mock_stt_client.initialise = AsyncMock(return_value=mock_init_response)
    mock_stt_client.create_job = AsyncMock()

    mock_client = MagicMock()
    mock_client.speech_to_text_job = mock_stt_client

    settings = MagicMock()
    settings.sarvam_stt_model = "saaras:v3"
    settings.sarvam_stt_language = "unknown"
    settings.sarvam_stt_mode = "transcribe"

    with (
        patch("app.providers.sarvam_stt_batch.AsyncSarvamAI", return_value=mock_client),
        patch("app.providers.sarvam_stt_batch.get_settings", return_value=settings),
        patch("app.providers.sarvam_stt_batch.AsyncSpeechToTextJob", return_value=mock_job),
    ):
        job_id, job = await submit_batch_job("test-key", "/tmp/audio.wav")

    mock_stt_client.create_job.assert_not_called()
    mock_stt_client.initialise.assert_awaited_once()
    init_kwargs = mock_stt_client.initialise.await_args.kwargs
    assert init_kwargs["job_parameters"]["model"] == "saaras:v3"
    assert init_kwargs["job_parameters"]["mode"] == "translate"
    mock_job.upload_files.assert_awaited_once_with(file_paths=["/tmp/audio.wav"])
    mock_job.start.assert_awaited_once()
    assert job_id == "batch-new"
    assert job is mock_job
