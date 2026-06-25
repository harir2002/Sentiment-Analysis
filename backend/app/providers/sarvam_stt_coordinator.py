"""Shared Sarvam STT state so duplicate pipelines reuse one batch job per audio file + language."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.providers.base import TranscriptionResult
from app.services.stt_language import AUTO_DETECT_CODE, cache_key_for_language


@dataclass
class SarvamSttSharedState:
    audio_path: str
    language_code: str = AUTO_DETECT_CODE
    batch_job_id: str | None = None
    status: str = "queued"
    transcript: str | None = None
    error: str | None = None
    raw_response: str | None = None
    runtime_seconds: float = 0.0
    status_message: str | None = None
    pending_background: bool = False
    waiters: list[asyncio.Future] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_states: dict[str, SarvamSttSharedState] = {}
_registry_lock = asyncio.Lock()


def _state_key(audio_path: str, language_code: str | None) -> str:
    return f"{audio_path}::{cache_key_for_language(language_code)}"


async def get_shared_state(audio_path: str, language_code: str | None = None) -> SarvamSttSharedState:
    key = cache_key_for_language(language_code)
    async with _registry_lock:
        if key not in _states:
            _states[key] = SarvamSttSharedState(
                audio_path=audio_path,
                language_code=key,
            )
        return _states[key]


def clear_shared_state(audio_path: str, language_code: str | None = None) -> None:
    if language_code is not None:
        _states.pop(_state_key(audio_path, language_code), None)
        return

    legacy_key = audio_path
    prefix = f"{audio_path}::"
    for key in list(_states.keys()):
        if key == legacy_key or key.startswith(prefix):
            _states.pop(key, None)


async def notify_waiters(state: SarvamSttSharedState, result: TranscriptionResult) -> None:
    for fut in state.waiters:
        if not fut.done():
            fut.set_result(result)
    state.waiters.clear()


def shared_to_result(state: SarvamSttSharedState) -> TranscriptionResult:
    return TranscriptionResult(
        transcript=state.transcript or "",
        runtime_seconds=state.runtime_seconds,
        provider="sarvam_stt",
        error=state.error,
        raw_response=state.raw_response,
        status=state.status,
        batch_job_id=state.batch_job_id,
        pending_background=state.pending_background,
        status_message=state.status_message,
        language_code=state.language_code,
    )
