import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
T = TypeVar("T")


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    provider_name: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> httpx.Response:
    """POST with exponential backoff on rate limits and transient errors."""
    last_response: httpx.Response | None = None
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.post(url, **kwargs)
            last_response = response

            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < max_retries
            ):
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s HTTP %s — retry %s/%s in %.1fs",
                    provider_name,
                    response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            return response

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s timeout/connect error — retry %s/%s in %.1fs: %s",
                    provider_name,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue
            raise

    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{provider_name}: request failed with no response")


async def run_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    provider_name: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retry_on: Callable[[Exception], bool] | None = None,
) -> T:
    """Run an async operation with retries for rate-limit style failures."""
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            should_retry = retry_on(exc) if retry_on else _is_retryable_exception(exc)
            if should_retry and attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s operation failed — retry %s/%s in %.1fs: %s",
                    provider_name,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{provider_name}: operation failed")


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))


def format_http_error(provider_name: str, response: httpx.Response) -> str:
    detail = response.text[:800] if response.text else response.reason_phrase
    status_label = "rate limited" if response.status_code == 429 else "HTTP error"
    return f"{provider_name} {status_label} ({response.status_code}): {detail}"
