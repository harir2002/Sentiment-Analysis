"""Sarvam batch STT: submit, poll, fetch — never block for 600s."""
from __future__ import annotations

import asyncio
import inspect
import logging
import tempfile
import time
from collections.abc import Coroutine
from typing import Any

import httpx

from sarvamai import AsyncSarvamAI
from sarvamai.requests import SpeechToTextJobParametersParams
from sarvamai.speech_to_text_job.job import AsyncSpeechToTextJob

from app.core.config import Settings, get_settings
from app.providers.sarvam_stt_utils import parse_batch_output_dir
from app.services.stt_english import sarvam_mode_for_english_output

logger = logging.getLogger(__name__)


def _ensure_job_handle(job: Any, *, context: str) -> Any:
    """Reject coroutines mistaken for job handles (missing await)."""
    if inspect.iscoroutine(job) or isinstance(job, Coroutine):
        raise TypeError(
            f"{context}: expected AsyncSpeechToTextJob, got unawaited coroutine"
        )
    if not hasattr(job, "get_status"):
        raise TypeError(
            f"{context}: job object missing get_status (type={type(job).__name__})"
        )
    logger.debug("%s: job handle type=%s job_id=%s", context, type(job).__name__, getattr(job, "job_id", "?"))
    return job


def build_batch_job_parameters(
    settings: Settings,
    *,
    language_code: str | None = None,
) -> SpeechToTextJobParametersParams:
    """
    Build SpeechToTextJobParametersParams for batch initialise().
    Transcribe mode belongs in job_parameters.mode (saaras:v3 only), not create_job kwargs.
    """
    from app.services.stt_language import sarvam_api_language_code

    resolved = sarvam_api_language_code(language_code)
    english_mode = sarvam_mode_for_english_output(
        settings.sarvam_stt_model,
        settings.sarvam_stt_mode,
    )
    params: SpeechToTextJobParametersParams = {
        "model": settings.sarvam_stt_model,
        "language_code": resolved,
        "with_diarization": False,
    }
    model = (settings.sarvam_stt_model or "").lower()
    if english_mode and "saaras" in model:
        params["mode"] = english_mode  # type: ignore[typeddict-item]
    logger.info(
        "Sarvam batch job parameters mode=%s language_code=%s",
        params.get("mode", "default"),
        resolved,
    )
    return params


async def submit_batch_job(
    api_key: str,
    audio_path: str,
    *,
    language_code: str | None = None,
) -> tuple[str, object]:
    """Create, upload, and start a Sarvam batch STT job. Returns (job_id, job_handle)."""
    settings = get_settings()
    client = AsyncSarvamAI(api_subscription_key=api_key)
    stt_client = client.speech_to_text_job
    job_parameters = build_batch_job_parameters(settings, language_code=language_code)

    logger.info("Sarvam batch initialise payload (language forced): %s", job_parameters)

    response = await stt_client.initialise(job_parameters=job_parameters)
    job = AsyncSpeechToTextJob(job_id=response.job_id, client=stt_client)
    job = _ensure_job_handle(job, context="submit_batch_job.initialise")
    await job.upload_files(file_paths=[audio_path])
    await job.start()
    return job.job_id, job


async def poll_batch_job(job, *, max_wait_seconds: float, poll_interval: float) -> dict:
    """
    Poll until complete, failed, or max_wait_seconds elapsed.
    Returns dict with keys: done, failed, timed_out, job_state, error
    """
    job = _ensure_job_handle(job, context="poll_batch_job")
    start = time.perf_counter()
    delay = poll_interval
    last_state = "unknown"

    while True:
        status = await job.get_status()
        last_state = (status.job_state or "unknown").lower()
        logger.info("Sarvam batch job %s state=%s", job.job_id, last_state)

        if last_state == "completed":
            return {"done": True, "failed": False, "timed_out": False, "job_state": last_state}
        if last_state == "failed":
            return {
                "done": True,
                "failed": True,
                "timed_out": False,
                "job_state": last_state,
                "error": "Sarvam batch job failed",
            }

        elapsed = time.perf_counter() - start
        if elapsed >= max_wait_seconds:
            return {
                "done": False,
                "failed": False,
                "timed_out": True,
                "job_state": last_state,
            }

        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 30.0)


async def download_batch_result_files(
    *,
    job: Any,
    stt_client: Any,
    output_files: list[str],
    output_dir: str,
) -> tuple[list[str], str | None]:
    """
    Download Sarvam batch output files using the batch download-files endpoint.

    We use the SDK's `get_download_links()`, which issues:
      POST /speech-to-text/job/v1/download-files

    Returns (downloaded_files, error).
    """
    try:
        # Documented payload to download-files endpoint:
        #   { "job_id": job.job_id, "files": output_files }
        logger.info(
            "Sarvam batch download-files payload job_id=%s files=%s",
            job.job_id,
            output_files,
        )
        download_links = await stt_client.get_download_links(
            job_id=job.job_id,
            files=output_files,
        )
    except Exception as exc:
        logger.exception("Sarvam batch get_download_links failed")
        return [], f"Sarvam STT batch download-files failed: {exc}"

    download_urls = getattr(download_links, "download_urls", {}) or {}
    logger.info(
        "Sarvam batch download-links response job_id=%s keys=%s",
        getattr(download_links, "job_id", job.job_id),
        list(download_urls.keys()),
    )

    downloaded: list[str] = []
    async with httpx.AsyncClient(timeout=180.0) as client:
        for file_name in output_files:
            details = download_urls.get(file_name)
            file_url = getattr(details, "file_url", None) if details else None
            if not file_url:
                logger.warning(
                    "Sarvam batch missing presigned URL for file=%s",
                    file_name,
                )
                continue

            out_path = f"{output_dir}/{file_name}"
            try:
                resp = await client.get(file_url)
                resp.raise_for_status()
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                downloaded.append(file_name)
            except Exception as exc:
                logger.exception(
                    "Sarvam batch failed downloading file_url file=%s",
                    file_name,
                )
                return downloaded, f"Sarvam STT batch download failed for {file_name}: {exc}"

    return downloaded, None


async def fetch_batch_transcript(job) -> tuple[str, str | None]:
    """
    Fetch transcript for a completed Sarvam batch job.

    Important: the Sarvam SDK does not expose `job.get_file_results()` in this environment,
    so we:
      1) fetch latest status via `job.get_status()`
      2) extract output filenames from `job_details[].outputs[].file_name`
      3) call the download-files endpoint (via SDK `get_download_links`)
      4) download each presigned file_url and parse transcript JSONs
    """
    job = _ensure_job_handle(job, context="fetch_batch_transcript")

    status = await job.get_status()
    job_state = (getattr(status, "job_state", None) or "unknown").lower()
    logger.info(
        "Sarvam batch fetch_transcript job_id=%s state=%s",
        getattr(job, "job_id", "?"),
        job_state,
    )

    job_details = getattr(status, "job_details", None) or []
    output_files: list[str] = []
    for task in job_details:
        outputs = getattr(task, "outputs", None) or []
        for out in outputs:
            file_name = getattr(out, "file_name", None)
            if file_name:
                output_files.append(str(file_name))

    # De-dupe while preserving order
    seen: set[str] = set()
    output_files = [f for f in output_files if not (f in seen or seen.add(f))]

    logger.info(
        "Sarvam batch job_id=%s output_files=%s",
        getattr(job, "job_id", "?"),
        output_files,
    )

    if not output_files:
        return "", "Sarvam STT batch completed but no output files were found"

    stt_client = getattr(job, "_client", None)
    if stt_client is None:
        return "", "Sarvam STT batch client missing internal _client; cannot download outputs"

    with tempfile.TemporaryDirectory() as tmp:
        downloaded_files, dl_err = await download_batch_result_files(
            job=job,
            stt_client=stt_client,
            output_files=output_files,
            output_dir=tmp,
        )
        if dl_err:
            return "", dl_err
        if not downloaded_files:
            return "", "Sarvam STT batch download returned no files"

        transcript = parse_batch_output_dir(tmp)

    if not transcript:
        return "", "Sarvam STT batch returned an empty transcript"

    return transcript, None


async def resume_batch_job(api_key: str, batch_job_id: str):
    """Reconstruct job handle for an existing batch job id."""
    client = AsyncSarvamAI(api_subscription_key=api_key)
    job = await client.speech_to_text_job.get_job(batch_job_id)
    return _ensure_job_handle(job, context="resume_batch_job")
