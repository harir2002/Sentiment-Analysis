import logging
import time

import httpx

from app.core.config import get_settings
from app.providers.base import AnalysisOutput
from app.providers.http_retry import format_http_error, post_with_retry
from app.providers.prompts import (
    SYSTEM_PROMPT,
    build_analysis_output,
    build_analysis_prompt,
    extract_llm_content,
    failed_analysis_output,
    safe_parse_llm_json,
    validate_analysis_json,
)
from app.services.guardrails import validate_transcript_for_analysis, get_max_transcript_chars

logger = logging.getLogger(__name__)


async def run_chat_completion(
    *,
    provider_name: str,
    url: str,
    headers: dict,
    payload: dict,
    timeout: float = 180.0,
) -> AnalysisOutput:
    settings = get_settings()
    start = time.perf_counter()
    retry_count = 0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await post_with_retry(
                client,
                url,
                provider_name=provider_name,
                max_retries=settings.api_max_retries,
                base_delay=settings.api_retry_base_seconds,
                headers=headers,
                json=payload,
            )

            if response.status_code == 429:
                retry_count = settings.api_max_retries
                return failed_analysis_output(
                    provider_name,
                    format_http_error(provider_name, response),
                    time.perf_counter() - start,
                    raw_response=response.text[:4000],
                )

            response.raise_for_status()
            data = response.json()
            content = extract_llm_content(data)

            if not content.strip():
                return failed_analysis_output(
                    provider_name,
                    f"{provider_name} returned an empty response",
                    time.perf_counter() - start,
                    raw_response=str(data)[:4000],
                )

            parsed = safe_parse_llm_json(content)
            if parsed.error or parsed.data is None:
                return failed_analysis_output(
                    provider_name,
                    f"{provider_name} JSON parse failed",
                    time.perf_counter() - start,
                    raw_response=parsed.raw_text[:4000],
                    parse_error=parsed.error,
                )

            validated, validation_error = validate_analysis_json(parsed.data)
            if validation_error:
                logger.warning(
                    "%s schema validation warning: %s",
                    provider_name,
                    validation_error,
                )
                # Use repaired data instead of failing
                if validated:
                    logger.info("Using repaired analysis data from %s", provider_name)
                    output = build_analysis_output(
                        validated, provider_name, time.perf_counter() - start
                    )
                    output.notes = "Analysis completed with data repair"
                    return output
                # If still invalid, use fallback
                logger.warning("Validation failed for %s, using fallback analysis", provider_name)
                from app.providers.prompts import safe_fallback_analysis_output
                return safe_fallback_analysis_output(provider_name, time.perf_counter() - start)

            output = build_analysis_output(
                validated, provider_name, time.perf_counter() - start
            )
            output.retry_count = retry_count
            return output

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response else 0
        detail = (
            format_http_error(provider_name, exc.response)
            if exc.response
            else str(exc)
        )
        out = failed_analysis_output(
            provider_name,
            detail,
            time.perf_counter() - start,
            raw_response=exc.response.text[:4000] if exc.response else None,
            status="rate_limited" if status == 429 else "failed",
            retry_count=settings.api_max_retries if status == 429 else retry_count,
        )
        return out

    except httpx.TimeoutException:
        return failed_analysis_output(
            provider_name,
            f"{provider_name} request timed out",
            time.perf_counter() - start,
        )

    except Exception as exc:
        logger.exception("%s unexpected error", provider_name)
        return failed_analysis_output(
            provider_name,
            f"{provider_name} error: {exc}",
            time.perf_counter() - start,
        )


def build_llm_payload(model: str, transcript: str, *, attempt: int = 0) -> dict:
    prompt = build_analysis_prompt(transcript, attempt=attempt)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 1500,  # Reduced to prevent truncation
    }
