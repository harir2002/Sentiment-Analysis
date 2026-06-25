import json
import logging
import time
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.providers.base import STTProvider, TranscriptionResult
from app.providers.http_retry import format_http_error, post_with_retry
from app.services.audio_validation import get_mime_type
from app.services.stt_language import (
    infer_detected_language_code,
    log_stt_language_event,
    analyze_transcript_language,
)

logger = logging.getLogger(__name__)


class GroqWhisperAdapter(STTProvider):
    name = "groq_whisper"

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

        logger.info(
            "Groq Whisper translate-to-English starting audio=%s endpoint=%s",
            audio_path,
            settings.groq_stt_translate_url,
        )

        try:
            api_key = settings.require_groq_key()
        except ValueError as e:
            return TranscriptionResult(
                transcript="",
                runtime_seconds=0.0,
                provider=self.name,
                error=str(e),
                status="failed",
            )

        try:
            mime = get_mime_type(audio_path)
            async with httpx.AsyncClient(timeout=180.0) as client:
                with open(audio_path, "rb") as f:
                    files = {"file": (Path(audio_path).name, f, mime)}
                    data = {
                        "model": settings.groq_stt_model,
                        "response_format": "verbose_json",
                        "temperature": 0,
                    }
                    response = await post_with_retry(
                        client,
                        settings.groq_stt_translate_url,
                        provider_name="Groq Whisper Translate",
                        max_retries=settings.api_max_retries,
                        base_delay=settings.api_retry_base_seconds,
                        headers={"Authorization": f"Bearer {api_key}"},
                        files=files,
                        data=data,
                    )

                if response.status_code == 429:
                    return TranscriptionResult(
                        transcript="",
                        runtime_seconds=time.perf_counter() - start,
                        provider=self.name,
                        error=format_http_error("Groq Whisper Translate", response),
                        raw_response=response.text[:4000],
                        status="rate_limited",
                        retry_count=settings.api_max_retries,
                    )

                response.raise_for_status()
                payload = response.json()
                raw = json.dumps(payload)[:4000]
                transcript = payload.get("text", "")
                whisper_detected = payload.get("language")

                inferred = infer_detected_language_code(
                    whisper_detected=whisper_detected,
                    transcript=transcript,
                )
                analysis = analyze_transcript_language(transcript)

                log_stt_language_event(
                    provider=self.name,
                    audio_path=audio_path,
                    mode="translate-to-english",
                    transcript=transcript,
                    whisper_detected_language=whisper_detected,
                    inferred_language=inferred,
                    phase="complete",
                )

                if not transcript:
                    return TranscriptionResult(
                        transcript="",
                        runtime_seconds=time.perf_counter() - start,
                        provider=self.name,
                        error="Groq Whisper returned an empty English translation",
                        raw_response=raw,
                        status="failed",
                        whisper_detected_language=whisper_detected,
                    )

                return TranscriptionResult(
                    transcript=transcript,
                    runtime_seconds=time.perf_counter() - start,
                    provider=self.name,
                    raw_response=raw,
                    language_code=inferred,
                    detected_script=analysis["dominant_script"],
                    whisper_detected_language=whisper_detected,
                )

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else 0
            return TranscriptionResult(
                transcript="",
                runtime_seconds=time.perf_counter() - start,
                provider=self.name,
                error=(
                    format_http_error("Groq Whisper Translate", e.response)
                    if e.response
                    else str(e)
                ),
                raw_response=e.response.text[:4000] if e.response else None,
                status="rate_limited" if status == 429 else "failed",
                retry_count=settings.api_max_retries if status == 429 else 0,
            )
        except httpx.TimeoutException:
            return TranscriptionResult(
                transcript="",
                runtime_seconds=time.perf_counter() - start,
                provider=self.name,
                error="Groq Whisper translation request timed out",
                status="failed",
            )
        except Exception as e:
            logger.exception("Groq Whisper translate error")
            return TranscriptionResult(
                transcript="",
                runtime_seconds=time.perf_counter() - start,
                provider=self.name,
                error=f"Groq Whisper translation error: {e}",
                status="failed",
            )
