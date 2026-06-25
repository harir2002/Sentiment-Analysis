"""Background worker: finish Sarvam batch STT and complete LLM analysis."""
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
from app.providers.sarvam_stt_coordinator import clear_shared_state
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
    infer_detected_language_code,
    log_stt_language_event,
)

logger = logging.getLogger(__name__)


async def schedule_sarvam_batch_followups(
    comparison_job_id: str,
    audio_path: str,
    results: list[ProviderResult],
) -> None:
    """Start background polling for any Sarvam STT batch jobs still in progress."""
    # For single-solution, results is now a single ProviderResult (converted to list for compatibility)
    if not results or not results[0].sarvam_batch_job_id:
        return

    result = results[0]
    batch_job_id = result.sarvam_batch_job_id
    
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

    logger.info("=" * 80)
    logger.info("🔄 BACKGROUND BATCH WORKER STARTED")
    logger.info("   Job ID: %s", comparison_job_id)
    logger.info("   Batch Job ID: %s", batch_job_id)
    logger.info("   Audio Path: %s", audio_path)
    logger.info("=" * 80)

    try:
        api_key = settings.require_sarvam_key()
    except ValueError as e:
        logger.error("❌ Sarvam batch worker missing API key: %s", e)
        return

    try:
        job = await resume_batch_job(api_key, batch_job_id)
        logger.info(
            "Sarvam batch worker resumed job %s (handle type=%s)",
            batch_job_id,
            type(job).__name__,
        )

        while True:
            status = await job.get_status()
            job_state = (status.job_state or "unknown").lower()
            elapsed = time.perf_counter() - worker_start
            
            # Calculate progress percentage (0-60% for STT, 60-90% for LLM prep)
            progress_percent = min(20 + int((elapsed / settings.sarvam_batch_max_wait_seconds) * 60), 60)
            progress_bar = "█" * (progress_percent // 5) + "░" * (20 - progress_percent // 5)
            logger.info(f"[{progress_bar}] {progress_percent}% - Transcribing audio ({int(elapsed)}s)...")

            if job_state == "completed":
                logger.info("[████████████████████] 60% - Batch completed, fetching transcript...")
                transcript, err = await fetch_batch_transcript(job)
                stt_runtime = time.perf_counter() - worker_start
                if err:
                    logger.error("❌ Failed to fetch batch transcript: %s", err)
                    await _update_sarvam_providers(
                        comparison_job_id, audio_path, None, err, "failed"
                    )
                    return
                logger.info("[████████████████████] 70% - Transcript fetched, starting LLM analysis...")
                logger.info("🤖 Starting LLM Analysis on background worker...")
                await _update_sarvam_providers(
                    comparison_job_id, audio_path, transcript, None, "completed", stt_runtime
                )
                logger.info("[██████████████████████] 100% - Analysis complete!")
                return

            if job_state == "failed":
                logger.error("❌ BATCH JOB FAILED")
                err = "Sarvam batch job failed"
                await _update_sarvam_providers(
                    comparison_job_id, audio_path, None, err, "failed"
                )
                return

            if (
                not timed_out_marked
                and elapsed >= settings.sarvam_batch_max_wait_seconds
            ):
                logger.warning("[████████████████████] 100% - Batch timeout, marking as completed")
                timed_out_marked = True
                await _update_sarvam_providers(
                    comparison_job_id,
                    audio_path,
                    None,
                    BATCH_UI_MESSAGE,
                    "timed_out",
                )

            if elapsed >= settings.sarvam_batch_absolute_max_seconds:
                logger.error("❌ BATCH JOB EXCEEDED ABSOLUTE MAX WAIT")
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
    from app.services.jobs import get_job
    from app.services.storage import delete_audio_file

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        job = await get_job(db, comparison_job_id)
        if not job or not job.result:
            return

        result = ProviderResult(**job.result)

        if stt_status == "timed_out":
            result.status = "timed_out"
            result.error = error
            result.status_message = error
        elif stt_status != "completed":
            result.status = "failed"
            result.error = error
            result.status_message = error
        elif result.status != "completed":
            try:
                solution = SolutionOption(result.solution_id)
            except ValueError:
                return
            
            _, llm_name = SOLUTION_CONFIG[solution]
            result.transcript = transcript or ""
            result.stt_runtime_seconds = stt_runtime
            result.status_message = None
            result.error = None

            if not result.transcript.strip():
                result.status = "failed"
                result.error = "Empty transcript from Sarvam batch"
            else:
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
                else:
                    result.transcript = normalize_english_transcript(result.transcript)
                    logger.info("[████████████████████░] 80% - Running LLM analysis...")
                    llm_start = time.perf_counter()
                    llm_result = await analyze_transcript(result.transcript, llm_name)
                    llm_elapsed = time.perf_counter() - llm_start
                    _apply_llm_result(result, llm_result)
                    result.total_runtime_seconds = (
                        result.stt_runtime_seconds + result.llm_runtime_seconds
                    )
                    result.status = "completed"
                    
                    logger.info("[██████████████████████] 100% - Analysis Complete! (LLM took %.1fs)", llm_elapsed)
                    logger.info("✅ Results:")
                    logger.info("   Sentiment: %s", result.analysis.sentiment if result.analysis else "N/A")
                    if result.analysis:
                        logger.info("   Confidence: %.0f%%", result.analysis.confidence * 100)
                        logger.info("   Key Issues: %s", ", ".join(result.analysis.key_issues or []))
                        logger.info("   Recommended Action: %s", result.analysis.recommended_action or "N/A")

        # Store result in database
        job.result = result.model_dump()
        detected = result.stt_language_code
        if detected:
            job.stt_language_code = detected
        job.completed_at = datetime.utcnow()
        job.total_runtime_seconds = result.total_runtime_seconds
        job.status = "completed" if result.status == "completed" else "running"

        if settings.cleanup_audio_after_job and audio_path and result.status == "completed":
            delete_audio_file(audio_path)
            job.audio_path = None

        await db.commit()
        logger.info(
            "Updated comparison job %s (Sarvam status=%s, detected_language=%s)",
            comparison_job_id,
            stt_status,
            job.stt_language_code,
        )
