import time

from app.core.config import get_settings
from app.providers.base import LLMProvider, AnalysisOutput
from app.providers.llm_common import build_llm_payload, run_chat_completion
from app.providers.prompts import failed_analysis_output
from app.services.guardrails import validate_transcript_for_analysis, get_max_transcript_chars


class OpenRouterGemmaAdapter(LLMProvider):
    name = "openrouter_gemma"

    async def analyze(self, transcript: str) -> AnalysisOutput:
        settings = get_settings()
        start = time.perf_counter()

        try:
            api_key = settings.require_openrouter_key()
        except ValueError as e:
            return failed_analysis_output(self.name, str(e), 0.0)

        if not (transcript or "").strip():
            return failed_analysis_output(
                self.name,
                "Cannot analyze an empty transcript",
                time.perf_counter() - start,
            )

        guardrail_error = validate_transcript_for_analysis(
            transcript,
            max_chars=get_max_transcript_chars(),
        )
        if guardrail_error:
            return failed_analysis_output(
                self.name,
                guardrail_error,
                time.perf_counter() - start,
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name

        return await run_chat_completion(
            provider_name="Groq Gemma 4 26B A4B (OpenRouter)",
            url=settings.openrouter_llm_url,
            headers=headers,
            payload=build_llm_payload(settings.openrouter_llm_model, transcript),
            timeout=120.0,
        )
