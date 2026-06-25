import logging
import time

import httpx

from app.core.config import SARVAM_LLM_DEFAULT_MAX_TOKENS, get_settings
from app.providers.base import LLMProvider, AnalysisOutput
from app.providers.http_retry import format_http_error, post_with_retry
from app.providers.prompts import (
    SARVAM_SYSTEM_PROMPT,
    build_analysis_output,
    build_sarvam_analysis_prompt,
    extract_llm_content,
    extract_llm_finish_reason,
    extract_llm_usage,
    failed_analysis_output,
    safe_parse_llm_json,
    validate_analysis_json,
)
from app.services.guardrails import (
    get_max_transcript_chars,
    shorten_transcript,
    validate_transcript_for_analysis,
)

logger = logging.getLogger(__name__)

PROVIDER_LABEL = "Sarvam LLM"


def resolve_sarvam_max_tokens(*, attempt: int = 0) -> int:
    """Return a plan-safe max_tokens value. Never exceeds the configured tier cap."""
    del attempt  # retries use transcript shortening instead of raising max_tokens
    settings = get_settings()
    return settings.sarvam_llm_token_limit


TRANSCRIPT_SHORTENED_MARKER = "\n\n[... transcript shortened for Sarvam analysis ...]\n\n"


def shorten_transcript_for_sarvam(transcript: str, *, attempt: int, max_chars: int) -> str:
    """Trim long transcripts on retry instead of requesting more output tokens."""
    return shorten_transcript(transcript, attempt=attempt, max_chars=max_chars)


def build_sarvam_llm_payload(
    model: str,
    transcript: str,
    *,
    max_tokens: int,
    retry: bool = False,
    attempt: int = 0,
) -> dict:
    settings = get_settings()
    safe_max_tokens = min(max_tokens, settings.sarvam_llm_token_limit)
    user_content = build_sarvam_analysis_prompt(transcript, retry=retry, attempt=attempt)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SARVAM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": safe_max_tokens,
    }


def _log_sarvam_request(attempt: int, payload: dict, transcript: str) -> None:
    messages = payload.get("messages") or []
    system_content = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    user_content = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    logger.info(
        "Sarvam LLM request attempt=%s model=%s max_tokens=%s "
        "system_chars=%s user_chars=%s transcript_chars=%s",
        attempt + 1,
        payload.get("model"),
        payload.get("max_tokens"),
        len(system_content),
        len(user_content),
        len(transcript or ""),
    )
    logger.debug("Sarvam LLM request payload: %s", payload)


def _log_sarvam_response(
    attempt: int,
    data: dict,
    content: str,
    finish_reason: str | None,
) -> None:
    usage = extract_llm_usage(data)
    logger.info(
        "Sarvam LLM response attempt=%s finish_reason=%s content_len=%s usage=%s",
        attempt + 1,
        finish_reason,
        len(content or ""),
        usage,
    )
    logger.debug("Sarvam LLM response metadata: %s", data)


def _is_retryable_response(
    content: str | None,
    finish_reason: str | None,
    parse_error: str | None,
    validation_error: str | None,
) -> bool:
    if finish_reason == "length":
        return True
    if content is None or not str(content).strip():
        return True
    if parse_error or validation_error:
        return True
    return False


def _is_max_tokens_limit_error(response: httpx.Response | None) -> bool:
    if response is None or response.status_code != 400:
        return False
    body = (response.text or "").lower()
    return "max_tokens" in body and "exceed" in body


def _max_tokens_limit_message(settings) -> str:
    return (
        f"Sarvam LLM max_tokens exceeds your plan limit for {settings.sarvam_llm_model} "
        f"({settings.sarvam_llm_plan_tier} tier). "
        f"Configured limit is {settings.sarvam_llm_token_limit} tokens."
    )


async def run_sarvam_chat_completion(transcript: str) -> AnalysisOutput:
    settings = get_settings()
    start = time.perf_counter()
    max_attempts = max(1, settings.sarvam_llm_content_retries)
    max_tokens = resolve_sarvam_max_tokens()
    max_chars = min(settings.sarvam_llm_max_transcript_chars, get_max_transcript_chars())

    guardrail_error = validate_transcript_for_analysis(transcript, max_chars=max_chars)
    if guardrail_error:
        return failed_analysis_output(PROVIDER_LABEL, guardrail_error, time.perf_counter() - start)

    last_error = "Sarvam LLM returned an empty response"
    last_raw: str | None = None
    last_parse_error: str | None = None
    retry_count = 0

    try:
        api_key = settings.require_sarvam_key()
    except ValueError as exc:
        return failed_analysis_output(PROVIDER_LABEL, str(exc), 0.0)

    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    logger.info(
        "Sarvam LLM using max_tokens=%s plan_tier=%s model=%s",
        max_tokens,
        settings.sarvam_llm_plan_tier,
        settings.sarvam_llm_model,
    )

    for attempt in range(max_attempts):
        payload = build_sarvam_llm_payload(
            settings.sarvam_llm_model,
            transcript,
            max_tokens=max_tokens,
            retry=attempt > 0,
            attempt=attempt,
        )
        attempt_transcript = transcript
        _log_sarvam_request(attempt, payload, attempt_transcript)

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await post_with_retry(
                    client,
                    settings.sarvam_llm_url,
                    provider_name=PROVIDER_LABEL,
                    max_retries=settings.api_max_retries,
                    base_delay=settings.api_retry_base_seconds,
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 429:
                    return failed_analysis_output(
                        PROVIDER_LABEL,
                        format_http_error(PROVIDER_LABEL, response),
                        time.perf_counter() - start,
                        raw_response=response.text[:4000],
                        status="rate_limited",
                        retry_count=settings.api_max_retries,
                    )

                if _is_max_tokens_limit_error(response):
                    return failed_analysis_output(
                        PROVIDER_LABEL,
                        _max_tokens_limit_message(settings),
                        time.perf_counter() - start,
                        raw_response=response.text[:4000],
                        retry_count=retry_count,
                    )

                response.raise_for_status()
                data = response.json()
                content = extract_llm_content(data)
                finish_reason = extract_llm_finish_reason(data)
                _log_sarvam_response(attempt, data, content, finish_reason)

                if content is None or not str(content).strip():
                    last_error = (
                        "Sarvam LLM returned empty content"
                        f"{f' (finish_reason={finish_reason})' if finish_reason else ''}"
                    )
                    last_raw = str(data)[:4000]
                    if _is_retryable_response(content, finish_reason, None, None) and attempt < max_attempts - 1:
                        retry_count += 1
                        continue
                    return failed_analysis_output(
                        PROVIDER_LABEL,
                        last_error,
                        time.perf_counter() - start,
                        raw_response=last_raw,
                        retry_count=retry_count,
                    )

                parsed = safe_parse_llm_json(content)
                if parsed.error or parsed.data is None:
                    last_error = "Sarvam LLM JSON parse failed"
                    last_parse_error = parsed.error
                    last_raw = parsed.raw_text[:4000]
                    if _is_retryable_response(content, finish_reason, parsed.error, None) and attempt < max_attempts - 1:
                        retry_count += 1
                        continue
                    return failed_analysis_output(
                        PROVIDER_LABEL,
                        last_error,
                        time.perf_counter() - start,
                        raw_response=last_raw,
                        parse_error=last_parse_error,
                        retry_count=retry_count,
                    )

                validated, validation_error = validate_analysis_json(parsed.data)
                if validation_error:
                    logger.warning(
                        "Sarvam LLM schema validation warning on attempt=%s: %s",
                        attempt + 1,
                        validation_error,
                    )
                    # Don't fail - use repaired data
                    if validated:
                        logger.info("Using repaired analysis data despite validation warning")
                        output = build_analysis_output(
                            validated,
                            PROVIDER_LABEL,
                            time.perf_counter() - start,
                        )
                        output.retry_count = retry_count
                        output.notes = "Analysis completed with data repair"
                        return output
                    # If still invalid after repair, retry
                    if attempt < max_attempts - 1:
                        retry_count += 1
                        continue
                    # Final attempt failed - use fallback
                    logger.warning("All validation attempts failed, using fallback analysis")
                    from app.providers.prompts import safe_fallback_analysis_output
                    return safe_fallback_analysis_output(PROVIDER_LABEL, time.perf_counter() - start)

                if finish_reason == "length":
                    logger.warning(
                        "Sarvam LLM finish_reason=length but JSON validated on attempt=%s",
                        attempt + 1,
                    )

                output = build_analysis_output(
                    validated,
                    PROVIDER_LABEL,
                    time.perf_counter() - start,
                )
                output.retry_count = retry_count
                return output

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else 0
            if _is_max_tokens_limit_error(exc.response):
                return failed_analysis_output(
                    PROVIDER_LABEL,
                    _max_tokens_limit_message(settings),
                    time.perf_counter() - start,
                    raw_response=exc.response.text[:4000] if exc.response else None,
                    retry_count=retry_count,
                )
            detail = (
                format_http_error(PROVIDER_LABEL, exc.response)
                if exc.response
                else str(exc)
            )
            return failed_analysis_output(
                PROVIDER_LABEL,
                detail,
                time.perf_counter() - start,
                raw_response=exc.response.text[:4000] if exc.response else None,
                status="rate_limited" if status == 429 else "failed",
                retry_count=settings.api_max_retries if status == 429 else retry_count,
            )

        except httpx.TimeoutException:
            last_error = f"{PROVIDER_LABEL} request timed out"
            if attempt < max_attempts - 1:
                retry_count += 1
                continue
            return failed_analysis_output(
                PROVIDER_LABEL,
                last_error,
                time.perf_counter() - start,
                retry_count=retry_count,
            )

        except Exception as exc:
            logger.exception("%s unexpected error on attempt %s", PROVIDER_LABEL, attempt + 1)
            last_error = f"{PROVIDER_LABEL} error: {exc}"
            if attempt < max_attempts - 1:
                retry_count += 1
                continue

    # All retries exhausted - use fallback instead of complete failure
    logger.warning(
        "Sarvam LLM exhausted all retries (attempts=%s), using fallback analysis",
        max_attempts
    )
    from app.providers.prompts import safe_fallback_analysis_output
    fallback = safe_fallback_analysis_output(PROVIDER_LABEL, time.perf_counter() - start)
    fallback.notes = f"Fallback analysis after {max_attempts} attempts"
    return fallback


class SarvamLLMAdapter(LLMProvider):
    name = "sarvam_llm"

    async def analyze(self, transcript: str) -> AnalysisOutput:
        start = time.perf_counter()

        if not (transcript or "").strip():
            return failed_analysis_output(
                self.name,
                "Cannot analyze an empty transcript",
                time.perf_counter() - start,
            )

        return await run_sarvam_chat_completion(transcript)
