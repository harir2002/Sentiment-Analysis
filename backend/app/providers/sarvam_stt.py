import json
import logging
import time
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.providers.base import STTProvider, TranscriptionResult
from app.providers.http_retry import format_http_error, post_with_retry
from app.providers.sarvam_stt_batch import submit_batch_job
from app.providers.sarvam_stt_chunks import (
    can_chunk_audio,
    cleanup_chunk_files,
    split_wav_chunks,
)
from app.providers.sarvam_stt_coordinator import (
    get_shared_state,
    notify_waiters,
    shared_to_result,
)
from app.providers.sarvam_stt_utils import extract_transcript_from_json
from app.services.audio_validation import get_audio_duration_seconds, get_mime_type
from app.services.stt_english import sarvam_mode_for_english_output
from app.services.stt_language import (
    is_auto_detect,
    sarvam_api_language_code,
    extract_sarvam_detected_language,
    analyze_transcript_language,
    infer_detected_language_code,
    log_stt_language_event,
    cache_key_for_language,
)

logger = logging.getLogger(__name__)

SARVAM_REST_MAX_SECONDS = 30

BATCH_UI_MESSAGE = (
    "Sarvam batch processing is taking longer than expected. "
    "This provider is still running in the background. "
    "Other providers may complete first."
)


def _extract_transcript_from_json(data: dict) -> str:
    return extract_transcript_from_json(data)


def _failed_stt(
    provider: str,
    error: str,
    runtime: float,
    *,
    raw_response: str | None = None,
    status: str = "failed",
    retry_count: int = 0,
    batch_job_id: str | None = None,
    status_message: str | None = None,
    pending_background: bool = False,
) -> TranscriptionResult:
    return TranscriptionResult(
        transcript="",
        runtime_seconds=runtime,
        provider=provider,
        error=error,
        raw_response=raw_response,
        status=status,
        retry_count=retry_count,
        batch_job_id=batch_job_id,
        status_message=status_message,
        pending_background=pending_background,
    )


class SarvamSTTAdapter(STTProvider):
    name = "sarvam_stt"

    async def transcribe(
        self,
        audio_path: str,
        *,
        language_code: str | None = None,
        initial_prompt: str | None = None,
        force_chunked: bool = False,
    ) -> TranscriptionResult:
        settings = get_settings()
        start = time.perf_counter()
        api_language = sarvam_api_language_code(language_code)
        auto_mode = is_auto_detect(language_code)

        logger.info(
            "Sarvam STT starting mode=%s api_language_code=%s audio=%s",
            "auto-detect" if auto_mode else "locked",
            api_language,
            audio_path,
        )

        try:
            api_key = settings.require_sarvam_key()
        except ValueError as e:
            return _failed_stt(self.name, str(e), 0.0)

        if force_chunked and can_chunk_audio(audio_path):
            chunked = await self._transcribe_chunked(
                api_key, audio_path, settings, start, api_language, language_code
            )
            if chunked.transcript and not chunked.error:
                log_stt_language_event(
                    provider=self.name,
                    audio_path=audio_path,
                    mode="locked-retry",
                    transcript=chunked.transcript,
                    inferred_language=chunked.language_code,
                    phase="chunked-retry",
                )
            return chunked

        duration = get_audio_duration_seconds(audio_path)
        rest_max = settings.sarvam_rest_max_seconds

        if duration is not None and duration <= rest_max:
            rest_result = await self._transcribe_rest(
                api_key, audio_path, settings, start, api_language, language_code
            )
            if rest_result.error and "30 seconds" in (rest_result.error or "").lower():
                return await self._transcribe_long_audio(
                    api_key, audio_path, settings, start, language_code, force_chunked
                )
            return rest_result

        return await self._transcribe_long_audio(
            api_key, audio_path, settings, start, language_code, force_chunked
        )

    async def _transcribe_long_audio(
        self,
        api_key: str,
        audio_path: str,
        settings,
        start: float,
        language_code: str | None,
        force_chunked: bool = False,
    ) -> TranscriptionResult:
        cache_key = cache_key_for_language(language_code)
        state = await get_shared_state(audio_path, language_code)

        async with state.lock:
            if state.transcript and state.language_code == cache_key:
                cached = shared_to_result(state)
                analysis = analyze_transcript_language(cached.transcript)
                cached.detected_script = analysis["dominant_script"]
                return cached
            if state.batch_job_id and state.status in {"running", "queued", "timed_out"}:
                return shared_to_result(state)

            if (force_chunked or settings.sarvam_chunk_stt_enabled) and can_chunk_audio(audio_path):
                chunked = await self._transcribe_chunked(
                    api_key, audio_path, settings, start, sarvam_api_language_code(language_code), language_code
                )
                if chunked.transcript and not chunked.error:
                    state.transcript = chunked.transcript
                    state.language_code = cache_key
                    state.status = "completed"
                    state.runtime_seconds = chunked.runtime_seconds
                    state.raw_response = chunked.raw_response
                    await notify_waiters(state, chunked)
                    return chunked

            return await self._submit_batch_async(
                api_key, audio_path, settings, start, state, language_code
            )

    async def _submit_batch_async(
        self, api_key: str, audio_path: str, settings, start: float, state, language_code: str
    ) -> TranscriptionResult:
        """Submit batch job and return immediately — never block on wait_until_complete."""
        try:
            state.status = "queued"
            job_id, job = await submit_batch_job(
                api_key, audio_path, language_code=language_code
            )
            state.batch_job_id = job_id
            state.status = "running"
            state.pending_background = True
            state.status_message = (
                "Sarvam batch STT job submitted. "
                "Processing continues in the background."
            )
            state.runtime_seconds = time.perf_counter() - start

            # Optional tiny poll window (default 0) for audio that finishes very fast.
            blocking = settings.sarvam_batch_blocking_poll_seconds
            if blocking > 0:
                from app.providers.sarvam_stt_batch import fetch_batch_transcript, poll_batch_job

                poll = await poll_batch_job(
                    job,
                    max_wait_seconds=blocking,
                    poll_interval=settings.sarvam_batch_poll_interval,
                )
                if poll.get("done") and not poll.get("failed"):
                    transcript, err = await fetch_batch_transcript(job)
                    if transcript and not err:
                        state.transcript = transcript
                        state.language_code = language_code
                        state.status = "completed"
                        state.pending_background = False
                        state.status_message = None
                        state.runtime_seconds = time.perf_counter() - start
                        result = TranscriptionResult(
                            transcript=transcript,
                            runtime_seconds=state.runtime_seconds,
                            provider=self.name,
                            batch_job_id=job_id,
                            status="completed",
                            language_code=language_code,
                        )
                        await notify_waiters(state, result)
                        return result

            result = shared_to_result(state)
            await notify_waiters(state, result)
            return result

        except Exception as e:
            logger.exception("Sarvam batch STT submit error")
            state.status = "failed"
            state.error = f"Sarvam STT batch error: {e}"
            state.runtime_seconds = time.perf_counter() - start
            result = shared_to_result(state)
            await notify_waiters(state, result)
            return result

    async def _transcribe_chunked(
        self,
        api_key: str,
        audio_path: str,
        settings,
        start: float,
        api_language: str,
        language_code: str | None,
    ) -> TranscriptionResult:
        chunk_paths: list[str] = []
        try:
            chunk_paths = split_wav_chunks(audio_path, settings.sarvam_chunk_seconds)
            parts: list[str] = []
            for chunk_path in chunk_paths:
                result = await self._transcribe_rest(
                    api_key, chunk_path, settings, time.perf_counter(), api_language, language_code
                )
                if result.error or not result.transcript.strip():
                    return result
                parts.append(result.transcript.strip())

            transcript = "\n\n".join(parts)
            inferred = infer_detected_language_code(transcript=transcript)
            analysis = analyze_transcript_language(transcript)
            return TranscriptionResult(
                transcript=transcript,
                runtime_seconds=time.perf_counter() - start,
                provider=self.name,
                status="completed",
                language_code=inferred,
                detected_script=analysis["dominant_script"],
            )
        except Exception as e:
            logger.warning("Chunked Sarvam STT failed, falling back to batch: %s", e)
            return _failed_stt(self.name, str(e), time.perf_counter() - start)
        finally:
            cleanup_chunk_files(chunk_paths)

    async def _transcribe_rest(
        self,
        api_key: str,
        audio_path: str,
        settings,
        start: float,
        api_language: str,
        language_code: str | None,
    ) -> TranscriptionResult:
        try:
            mime = get_mime_type(audio_path)
            auto_mode = is_auto_detect(language_code)
            english_mode = sarvam_mode_for_english_output(
                settings.sarvam_stt_model,
                settings.sarvam_stt_mode,
            )
            logger.info(
                "Sarvam STT REST translate-to-English api_language_code=%s model=%s mode=%s",
                api_language,
                settings.sarvam_stt_model,
                english_mode,
            )
            async with httpx.AsyncClient(timeout=180.0) as client:
                with open(audio_path, "rb") as f:
                    files = {"file": (Path(audio_path).name, f, mime)}
                    headers = {"api-subscription-key": api_key}
                    rest_data = {
                        "model": settings.sarvam_stt_model,
                        "language_code": api_language,
                    }
                    if english_mode and "saaras" in (settings.sarvam_stt_model or "").lower():
                        rest_data["mode"] = english_mode
                    response = await post_with_retry(
                        client,
                        settings.sarvam_stt_url,
                        provider_name="Sarvam STT",
                        max_retries=settings.api_max_retries,
                        base_delay=settings.api_retry_base_seconds,
                        files=files,
                        headers=headers,
                        data=rest_data,
                    )

                if response.status_code == 429:
                    return _failed_stt(
                        self.name,
                        format_http_error("Sarvam STT", response),
                        time.perf_counter() - start,
                        raw_response=response.text[:4000],
                        status="rate_limited",
                        retry_count=settings.api_max_retries,
                    )

                response.raise_for_status()
                data = response.json()
                raw = json.dumps(data)[:4000]
                transcript = _extract_transcript_from_json(data)

                if not transcript:
                    return _failed_stt(
                        self.name,
                        "Sarvam STT returned an empty transcript",
                        time.perf_counter() - start,
                        raw_response=raw,
                    )

                sarvam_detected = extract_sarvam_detected_language(data)
                inferred = infer_detected_language_code(
                    sarvam_detected=sarvam_detected,
                    transcript=transcript,
                )
                analysis = analyze_transcript_language(transcript)
                log_stt_language_event(
                    provider=self.name,
                    audio_path=audio_path,
                    mode="translate-to-english",
                    transcript=transcript,
                    sarvam_detected_language=sarvam_detected,
                    inferred_language=inferred,
                    phase="rest-complete",
                )

                return TranscriptionResult(
                    transcript=transcript,
                    runtime_seconds=time.perf_counter() - start,
                    provider=self.name,
                    raw_response=raw,
                    status="completed",
                    language_code=inferred,
                    detected_script=analysis["dominant_script"],
                    sarvam_detected_language=sarvam_detected,
                )

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else 0
            return _failed_stt(
                self.name,
                format_http_error("Sarvam STT", e.response) if e.response else str(e),
                time.perf_counter() - start,
                raw_response=e.response.text[:4000] if e.response else None,
                status="rate_limited" if status == 429 else "failed",
                retry_count=settings.api_max_retries if status == 429 else 0,
            )
        except httpx.TimeoutException:
            return _failed_stt(
                self.name,
                "Sarvam STT request timed out",
                time.perf_counter() - start,
            )
        except Exception as e:
            logger.exception("Sarvam STT error")
            return _failed_stt(
                self.name,
                f"Sarvam STT error: {e}",
                time.perf_counter() - start,
            )
