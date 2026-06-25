"""Background worker: finish Sarvam batch STT and complete deferred provider pipelines."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.core.config import get_settings
from app.models.schemas import ProviderResult, SolutionOption
from app.providers.registry import SOLUTION_CONFIG
from app.providers.sarvam_stt import BATCH_UI_MESSAGE
from app.providers.sarvam_stt_batch import fetch_batch_transcript, resume_batch_job
from app.providers.sarvam_stt_coordinator import clear_shared_state, get_shared_state
from app.services.pipeline import (
    _apply_llm_result,
    _retry_english_translation,
    analyze_transcript,
)
from app.services.stt_english import (
    ENGLISH_TRANSLATION_FAILED,
    normalize_english_transcript,
    validate_english_transcript,
)
from app.services.stt_language import (
    AUTO_DETECT_CODE,
    analyze_transcript_language,
    consensus_detected_language,
    infer_detected_language_code,
    log_stt_language_event,
)

logger = logging.getLogger(__name__)

SARVAM_SOLUTIONS = {
    SolutionOption.SARVAM_SARVAM.value,
    SolutionOption.SARVAM_GROQ.value,
}


async def schedule_sarvam_batch_followups(
    comparison_job_id: str,
    audio_path: str,
    results: list[ProviderResult],
) -> None:
    """Start background polling for any Sarvam STT batch jobs still in progress."""
    pending = [
        r
        for r in results
        if r.solution_id in SARVAM_SOLUTIONS
        and r.status in {"running", "queued", "timed_out"}
        and r.sarvam_batch_job_id
    ]
    if not pending:
        return

    batch_job_id = pending[0].sarvam_batch_job_id
    asyncio.create_task(
        _background_batch_worker(comparison_job_id, audio_path, batch_job_id),
        name=f"sarvam-batch-{comparison_job_id}",
    )


async def _background_batch_worker(
    comparison_job_id: str,
    audio_path: str,
    batch_job_id: str,
) -> None:
    settings = get_settings()
    worker_start = time.perf_counter()
    timed_out_marked = False
    delay = settings.sarvam_batch_poll_interval

    try:
        api_key = settings.require_sarvam_key()
    except ValueError as e:
        logger.error("Sarvam batch worker missing API key: %s", e)
        return

    try:
        job = await resume_batch_job(api_key, batch_job_id)
        logger.info(
            "Sarvam batch worker resumed job %s (handle type=%s)",
            batch_job_id,
            type(job).__name__,
        )

        state = await get_shared_state(audio_path, None)

        while True:
            status = await job.get_status()
            job_state = (status.job_state or "unknown").lower()
            elapsed = time.perf_counter() - worker_start
            logger.info(
                "Sarvam batch %s state=%s elapsed=%.0fs",
                batch_job_id,
                job_state,
                elapsed,
            )

            if job_state == "completed":
                transcript, err = await fetch_batch_transcript(job)
                stt_runtime = time.perf_counter() - worker_start
                if err:
                    await _update_sarvam_providers(
                        comparison_job_id, audio_path, None, err, "failed"
                    )
                    return
                state.transcript = transcript
                state.language_code = AUTO_DETECT_CODE
                state.status = "completed"
                state.pending_background = False
                await _update_sarvam_providers(
                    comparison_job_id, audio_path, transcript, None, "completed", stt_runtime
                )
                return

            if job_state == "failed":
                err = "Sarvam batch job failed"
                await _update_sarvam_providers(
                    comparison_job_id, audio_path, None, err, "failed"
                )
                return

            if (
                not timed_out_marked
                and elapsed >= settings.sarvam_batch_max_wait_seconds
            ):
                timed_out_marked = True
                state.status = "timed_out"
                state.pending_background = True
                state.status_message = BATCH_UI_MESSAGE
                await _update_sarvam_providers(
                    comparison_job_id,
                    audio_path,
                    None,
                    BATCH_UI_MESSAGE,
                    "timed_out",
                )

            if elapsed >= settings.sarvam_batch_absolute_max_seconds:
                err = "Sarvam batch STT exceeded maximum wait time"
                await _update_sarvam_providers(
                    comparison_job_id, audio_path, None, err, "failed"
                )
                return

            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 30.0)

    except TypeError as e:
        logger.error("Sarvam batch worker invalid job handle for %s: %s", batch_job_id, e)
        await _update_sarvam_providers(
            comparison_job_id,
            audio_path,
            None,
            f"Sarvam batch worker error: {e}",
            "failed",
        )
    except Exception as e:
        logger.exception("Sarvam batch background worker failed")
        await _update_sarvam_providers(
            comparison_job_id, audio_path, None, str(e), "failed"
        )
    finally:
        clear_shared_state(audio_path)


async def _update_sarvam_providers(
    comparison_job_id: str,
    audio_path: str,
    transcript: str | None,
    error: str | None,
    stt_status: str,
    stt_runtime: float = 0.0,
) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services.jobs import get_job, _all_providers_completed, _pending_provider_count
    from app.services.storage import delete_audio_file

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        job = await get_job(db, comparison_job_id)
        if not job or not job.results:
            return

        results = [ProviderResult(**r) for r in job.results]

        for result in results:
            if result.solution_id not in SARVAM_SOLUTIONS:
                continue

            if stt_status == "timed_out":
                result.status = "timed_out"
                result.error = error
                result.status_message = error
                continue

            if stt_status != "completed":
                result.status = "failed"
                result.error = error
                result.status_message = error
                continue

            if result.status == "completed":
                continue

            try:
                solution = SolutionOption(result.solution_id)
            except ValueError:
                continue
            _, llm_name = SOLUTION_CONFIG[solution]
            result.transcript = transcript or ""
            result.stt_runtime_seconds = stt_runtime
            result.status_message = None
            result.error = None

            if not result.transcript.strip():
                result.status = "failed"
                result.error = "Empty transcript from Sarvam batch"
                continue

            inferred = infer_detected_language_code(transcript=result.transcript)
            analysis = analyze_transcript_language(result.transcript)
            result.stt_language_code = inferred
            result.detected_script = analysis["dominant_script"]

            log_stt_language_event(
                provider="sarvam_stt",
                audio_path=audio_path,
                mode="translate-to-english",
                transcript=result.transcript,
                inferred_language=inferred,
                phase="batch-complete",
            )

            english_error = validate_english_transcript(result.transcript)
            if english_error and job.audio_path:
                logger.warning(
                    "Sarvam batch English validation failed for job %s — internal retry",
                    comparison_job_id,
                )
                retry = await _retry_english_translation(
                    job.audio_path,
                    "sarvam_stt",
                )
                if retry.status == "completed" and (retry.transcript or "").strip():
                    retry_error = validate_english_transcript(retry.transcript)
                    if not retry_error:
                        result.transcript = normalize_english_transcript(retry.transcript)
                        result.stt_runtime_seconds += retry.runtime_seconds
                        result.retry_count = max(result.retry_count, retry.retry_count) + 1
                        result.stt_language_code = retry.language_code or inferred
                        result.detected_script = retry.detected_script
                        english_error = None

            if english_error:
                result.status = "failed"
                result.error = ENGLISH_TRANSLATION_FAILED
                result.transcript = ""
                continue

            result.transcript = normalize_english_transcript(result.transcript)

            llm_result = await analyze_transcript(result.transcript, llm_name)
            _apply_llm_result(result, llm_result)
            result.total_runtime_seconds = (
                result.stt_runtime_seconds + result.llm_runtime_seconds
            )

        # Single-solution mode: store first (primary) result only
        if results:
            job.result = results[0].model_dump()
            detected = results[0].stt_language_code
            if detected:
                job.stt_language_code = detected
            job.completed_at = datetime.utcnow()
            job.total_runtime_seconds = results[0].total_runtime_seconds
            job.status = "completed" if results[0].status == "completed" else "running"
        else:
            job.status = "failed"

        if _all_providers_completed(scored) and settings.cleanup_audio_after_job and job.audio_path:
            delete_audio_file(job.audio_path)
            job.audio_path = None

        await db.commit()
        logger.info(
            "Updated comparison job %s (Sarvam STT status=%s, pending=%s, detected_language=%s)",
            comparison_job_id,
            stt_status,
            pending,
            job.stt_language_code,
        )
