from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    transcript: str
    runtime_seconds: float
    provider: str
    error: str | None = None
    raw_response: str | None = None
    status: str = "completed"
    retry_count: int = 0
    batch_job_id: str | None = None
    pending_background: bool = False
    status_message: str | None = None
    language_code: str | None = None
    language_mismatch_warning: str | None = None
    detected_script: str | None = None
    whisper_detected_language: str | None = None
    sarvam_detected_language: str | None = None


@dataclass
class AnalysisOutput:
    sentiment: str
    key_issues: list[str]
    summary: str
    action_items: list[str]
    resolution_status: str
    confidence: float
    runtime_seconds: float
    provider: str
    notes: str = ""
    error: str | None = None
    raw_response: str | None = None
    parse_error: str | None = None
    status: str = "completed"
    retry_count: int = 0


class STTProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        *,
        language_code: str | None = None,
        initial_prompt: str | None = None,
        force_chunked: bool = False,
    ) -> TranscriptionResult:
        pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def analyze(self, transcript: str) -> AnalysisOutput:
        pass
