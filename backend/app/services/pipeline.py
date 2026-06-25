import logging
import time

from app.models.schemas import (
    SolutionOption,
    SOLUTION_LABELS,
    ProviderResult,
    AnalysisResult,
)
from app.services.recommended_action import enrich_analysis
from app.providers.registry import (
    get_stt_provider,
    get_llm_provider,
    SOLUTION_CONFIG,
    get_model_names,
)
from app.providers.sarvam_stt_coordinator import clear_shared_state
from app.services.audio_validation import validate_audio_file, AudioValidationError
from app.services.guardrails import (
    GUARDRAIL_USER_ERROR,
    get_max_transcript_chars,
    validate_transcript_for_analysis,
)
from app.services.stt_language import (
    infer_detected_language_code,
    log_stt_language_event,
    analyze_transcript_language,
)
from app.services.stt_english import (
    ENGLISH_TRANSLATION_FAILED,
    normalize_english_transcript,
    validate_english_transcript,
)

logger = logging.getLogger(__name__)


def make_failed_result(solution: SolutionOption, error: str) -> ProviderResult:
    stt_name, llm_name = SOLUTION_CONFIG[solution]
    stt_model, llm_model = get_model_names(stt_name, llm_name)
    return ProviderResult(
        solution_id=solution.value,
        label=SOLUTION_LABELS[solution],
        stt_provider=stt_name,
        llm_provider=llm_name,
        stt_model=stt_model,
        llm_model=llm_model,
        status="failed",
        error=error,
    )


def _attach_language_metadata(stt_result):
    """Keep detected source language internal for logging only."""
    if not stt_result.language_code:
        stt_result.language_code = infer_detected_language_code(
            whisper_detected=stt_result.whisper_detected_language,
            sarvam_detected=stt_result.sarvam_detected_language,
            transcript=stt_result.transcript,
        )
    analysis = analyze_transcript_language(stt_result.transcript or "")
    stt_result.detected_script = analysis["dominant_script"]
    return stt_result


async def _retry_english_translation(audio_path: str, provider_name: str):
    """Retry translate-to-English STT once after validation failure."""
    provider = get_stt_provider(provider_name)
    clear_shared_state(audio_path, None)

    kwargs: dict = {}
    if provider_name == "sarvam_stt":
        kwargs["force_chunked"] = True

    logger.warning(
        "STT English validation retry provider=%s",
        provider_name,
    )

    return await provider.transcribe(audio_path, language_code=None, **kwargs)


async def transcribe(audio_path: str, provider_name: str, *, language_code: str | None = None):
    del language_code  # always auto-detect source language internally

    log_stt_language_event(
        provider=provider_name,
        audio_path=audio_path,
        mode="translate-to-english",
        phase="start",
    )

    result = await get_stt_provider(provider_name).transcribe(
        audio_path, language_code=None
    )
    result = _attach_language_metadata(result)

    inferred = result.language_code
    log_stt_language_event(
        provider=provider_name,
        audio_path=audio_path,
        mode="translate-to-english",
        transcript=result.transcript,
        whisper_detected_language=result.whisper_detected_language,
        sarvam_detected_language=result.sarvam_detected_language,
        inferred_language=inferred,
        phase="complete",
    )

    if result.pending_background or result.status != "completed":
        return result

    if not (result.transcript or "").strip():
        return result

    english_error = validate_english_transcript(result.transcript)
    if not english_error:
        result.transcript = normalize_english_transcript(result.transcript)
        return result

    retry = await _retry_english_translation(audio_path, provider_name)
    retry = _attach_language_metadata(retry)
    retry.retry_count = max(retry.retry_count, result.retry_count) + 1

    log_stt_language_event(
        provider=provider_name,
        audio_path=audio_path,
        mode="translate-to-english",
        transcript=retry.transcript,
        whisper_detected_language=retry.whisper_detected_language,
        sarvam_detected_language=retry.sarvam_detected_language,
        inferred_language=retry.language_code,
        phase="retry-complete",
    )

    if retry.status == "completed" and (retry.transcript or "").strip():
        retry_error = validate_english_transcript(retry.transcript)
        if not retry_error:
            retry.transcript = normalize_english_transcript(retry.transcript)
            return retry

    result.status = "failed"
    result.error = ENGLISH_TRANSLATION_FAILED
    result.transcript = ""
    result.language_mismatch_warning = None
    return result


async def analyze_transcript(transcript: str, provider_name: str):
    provider = get_llm_provider(provider_name)
    return await provider.analyze(transcript)


def _apply_llm_result(result: ProviderResult, llm_result) -> ProviderResult:
    result.llm_runtime_seconds = llm_result.runtime_seconds
    result.raw_llm_response = llm_result.raw_response
    result.retry_count = max(result.retry_count, llm_result.retry_count)

    if llm_result.error:
        result.status = (
            "rate_limited"
            if llm_result.status == "rate_limited"
            else "failed"
        )
        result.error = llm_result.error
        result.parsing_error = llm_result.parse_error
        if llm_result.parse_error and llm_result.raw_response:
            result.error = f"{llm_result.error} | parse: {llm_result.parse_error}"
        return result

    result.analysis = enrich_analysis(
        AnalysisResult(
            sentiment=llm_result.sentiment,
            key_issues=llm_result.key_issues,
            summary=llm_result.summary,
            action_items=llm_result.action_items,
            resolution_status=llm_result.resolution_status,
            confidence=llm_result.confidence,
            notes=llm_result.notes,
        )
    )
    result.status = "completed"
    result.error = None
    result.parsing_error = None
    result.status_message = None
    return result


def _apply_stt_pending(result: ProviderResult, stt_result) -> ProviderResult:
    result.stt_runtime_seconds = stt_result.runtime_seconds
    result.raw_stt_response = stt_result.raw_response
    result.retry_count = max(result.retry_count, stt_result.retry_count)
    result.sarvam_batch_job_id = stt_result.batch_job_id
    result.status_message = stt_result.status_message
    result.status = stt_result.status
    result.error = stt_result.error
    result.transcript = stt_result.transcript or ""
    result.stt_language_code = stt_result.language_code
    result.language_mismatch_warning = stt_result.language_mismatch_warning
    result.detected_script = stt_result.detected_script
    result.whisper_detected_language = stt_result.whisper_detected_language
    return result


async def run_full_pipeline(
    audio_path: str,
    solution: SolutionOption,
    *,
    language_code: str | None = None,
) -> ProviderResult:
    stt_name, llm_name = SOLUTION_CONFIG[solution]
    stt_model, llm_model = get_model_names(stt_name, llm_name)
    label = SOLUTION_LABELS[solution]

    result = ProviderResult(
        solution_id=solution.value,
        label=label,
        stt_provider=stt_name,
        llm_provider=llm_name,
        stt_model=stt_model,
        llm_model=llm_model,
        status="running",
    )

    pipeline_start = time.perf_counter()

    try:
        validate_audio_file(audio_path)

        logger.info(
            "Pipeline %s starting translate-to-English STT provider=%s",
            solution.value,
            stt_name,
        )

        stt_result = await transcribe(audio_path, stt_name, language_code=language_code)
        result = _apply_stt_pending(result, stt_result)

        if stt_result.status in {"queued", "running", "timed_out"} and (
            stt_result.pending_background or not stt_result.transcript.strip()
        ):
            result.total_runtime_seconds = time.perf_counter() - pipeline_start
            return result

        if stt_result.error and stt_result.status not in {"timed_out", "rate_limited"}:
            result.error = (
                ENGLISH_TRANSLATION_FAILED
                if stt_result.status == "failed"
                else stt_result.error
            )
            result.total_runtime_seconds = time.perf_counter() - pipeline_start
            return result

        if not result.transcript.strip():
            result.status = "failed"
            result.error = ENGLISH_TRANSLATION_FAILED
            result.total_runtime_seconds = time.perf_counter() - pipeline_start
            return result

        english_error = validate_english_transcript(result.transcript)
        if english_error:
            result.status = "failed"
            result.error = english_error
            result.transcript = ""
            result.total_runtime_seconds = time.perf_counter() - pipeline_start
            return result

        result.transcript = normalize_english_transcript(result.transcript)

        guardrail_error = validate_transcript_for_analysis(
            result.transcript,
            max_chars=get_max_transcript_chars(),
        )
        if guardrail_error:
            result.status = "failed"
            result.error = guardrail_error
            result.total_runtime_seconds = time.perf_counter() - pipeline_start
            return result

        llm_result = await analyze_transcript(result.transcript, llm_name)
        result = _apply_llm_result(result, llm_result)
        result.total_runtime_seconds = time.perf_counter() - pipeline_start
        return result

    except AudioValidationError as e:
        result.status = "failed"
        result.error = str(e)
        result.total_runtime_seconds = time.perf_counter() - pipeline_start
        logger.warning("Pipeline %s audio validation failed: %s", solution.value, e)
        return result
    except Exception as e:
        result.status = "failed"
        result.error = GUARDRAIL_USER_ERROR if "guardrail" in str(e).lower() else str(e)
        result.total_runtime_seconds = time.perf_counter() - pipeline_start
        logger.exception("Pipeline %s failed", solution.value)
        return result
