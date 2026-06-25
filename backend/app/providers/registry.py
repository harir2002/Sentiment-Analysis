from app.core.config import get_settings
from app.providers.sarvam_stt import SarvamSTTAdapter
from app.providers.sarvam_llm import SarvamLLMAdapter
from app.providers.groq_whisper import GroqWhisperAdapter
from app.providers.openrouter_gemma import OpenRouterGemmaAdapter
from app.models.schemas import SolutionOption, SOLUTION_LABELS

STT_PROVIDERS = {
    "sarvam_stt": SarvamSTTAdapter,
    "groq_whisper": GroqWhisperAdapter,
}

LLM_PROVIDERS = {
    "sarvam_llm": SarvamLLMAdapter,
    "openrouter_gemma": OpenRouterGemmaAdapter,
}

SOLUTION_CONFIG = {
    SolutionOption.SARVAM_SARVAM: ("sarvam_stt", "sarvam_llm"),
    SolutionOption.SARVAM_GROQ: ("sarvam_stt", "openrouter_gemma"),
    SolutionOption.GROQ_SARVAM: ("groq_whisper", "sarvam_llm"),
    SolutionOption.GROQ_GROQ: ("groq_whisper", "openrouter_gemma"),
}


def get_stt_provider(name: str):
    return STT_PROVIDERS[name]()


def get_llm_provider(name: str):
    return LLM_PROVIDERS[name]()


def get_model_names(stt_provider: str, llm_provider: str) -> tuple[str, str]:
    settings = get_settings()
    stt_models = {
        "sarvam_stt": settings.sarvam_stt_model,
        "groq_whisper": settings.groq_stt_model,
    }
    llm_models = {
        "sarvam_llm": settings.sarvam_llm_model,
        "openrouter_gemma": settings.openrouter_llm_model,
    }
    return stt_models[stt_provider], llm_models[llm_provider]


def get_all_solutions():
    for opt in SolutionOption:
        stt_name, llm_name = SOLUTION_CONFIG[opt]
        stt_model, llm_model = get_model_names(stt_name, llm_name)
        yield {
            "solution_id": opt.value,
            "label": SOLUTION_LABELS[opt],
            "stt_provider": stt_name,
            "llm_provider": llm_name,
            "stt_model": stt_model,
            "llm_model": llm_model,
        }


def get_active_solution() -> str:
    """Return the configured active solution."""
    settings = get_settings()
    return settings.active_solution


def get_active_solution_config() -> tuple[str, str]:
    """Return (stt_provider_name, llm_provider_name) for active solution."""
    active = get_active_solution()
    try:
        config = SOLUTION_CONFIG[SolutionOption(active)]
    except (KeyError, ValueError):
        raise ValueError(f"Unknown active solution: {active}")
    return config
