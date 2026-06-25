import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError, ProviderConfigError
from app.core.observability import metrics, request_id_ctx

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        header = settings.request_id_header
        request_id = request.headers.get(header) or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics.record_request(
                status_code=500,
                latency_ms=elapsed_ms,
                slow_threshold_ms=settings.slow_request_threshold_ms,
            )
            request_id_ctx.reset(token)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.record_request(
            status_code=response.status_code,
            latency_ms=elapsed_ms,
            slow_threshold_ms=settings.slow_request_threshold_ms,
        )
        response.headers[header] = request_id
        logger.info(
            "request_completed method=%s path=%s status=%s latency_ms=%.0f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        if elapsed_ms >= settings.slow_request_threshold_ms:
            logger.warning(
                "slow_request method=%s path=%s latency_ms=%.0f request_id=%s",
                request.method,
                request.url.path,
                elapsed_ms,
                request_id,
            )
        request_id_ctx.reset(token)
        return response


def _error_body(request: Request, detail: str, *, error_code: str | None = None) -> dict:
    settings = get_settings()
    body: dict = {"detail": detail}
    if error_code:
        body["error_code"] = error_code
    rid = request.headers.get(settings.request_id_header) or request_id_ctx.get()
    if rid:
        body["request_id"] = rid
    return body


async def audio_validation_handler(request: Request, exc: AudioValidationError):
    metrics.record_upload(accepted=False)
    return JSONResponse(
        status_code=400,
        content=_error_body(request, str(exc), error_code="audio_validation_failed"),
    )


async def provider_config_handler(request: Request, exc: ProviderConfigError):
    return JSONResponse(
        status_code=503,
        content=_error_body(request, str(exc), error_code="provider_not_configured"),
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    settings = get_settings()
    logger.exception(
        "unhandled_exception method=%s path=%s",
        request.method,
        request.url.path,
    )
    detail = "Internal server error"
    body = _error_body(request, detail, error_code="internal_error")
    if settings.show_error_details:
        body["error"] = str(exc)
    return JSONResponse(status_code=500, content=body)
