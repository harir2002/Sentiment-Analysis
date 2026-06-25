import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging_config import configure_logging
from app.core.exceptions import AudioValidationError, ProviderConfigError
from app.core.middleware import (
    RequestLoggingMiddleware,
    audio_validation_handler,
    provider_config_handler,
    unhandled_exception_handler,
)
from app.api.routes import router

logger = logging.getLogger(__name__)

configure_logging(
    level=get_settings().log_level,
    access_log=get_settings().access_log,
    log_format=get_settings().log_format,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)
    await init_db()

    route_paths = sorted(
        {
            f"{','.join(sorted(route.methods))} {route.path}"
            for route in app.routes
            if getattr(route, "path", None) and getattr(route, "methods", None)
        }
    )
    logger.info("Registered %s API route(s)", len(route_paths))
    for route in route_paths:
        logger.info("API route loaded: %s", route)

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Call Analytics Comparison API",
        description="Compare Sarvam and Groq STT/LLM pipelines for call analysis",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(AudioValidationError, audio_validation_handler)
    app.add_exception_handler(ProviderConfigError, provider_config_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(router)
    return app


app = create_app()
