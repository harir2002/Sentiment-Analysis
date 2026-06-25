import asyncio
import logging

from app.core.observability import metrics, obs_logger
from app.models.schemas import SolutionOption, ProviderResult
from app.providers.registry import get_active_solution
from app.services.pipeline import run_full_pipeline, make_failed_result

logger = logging.getLogger(__name__)


async def _run_solution(
    solution: SolutionOption,
    audio_path: str,
    language_code: str | None = None,
) -> ProviderResult:
    try:
        return await run_full_pipeline(audio_path, solution, language_code=language_code)
    except Exception as exc:
        logger.exception("Pipeline %s failed", solution.value)
        return make_failed_result(solution, str(exc))


async def run_single_solution(
    audio_path: str,
    solution_id: str | None = None,
    language_code: str | None = None,
) -> ProviderResult:
    """Run single solution (production flow - no comparison or scoring)."""
    if solution_id is None:
        solution_id = get_active_solution()
    
    try:
        solution = SolutionOption(solution_id)
    except ValueError:
        raise ValueError(f"Unknown solution: {solution_id}")
    
    result = await _run_solution(solution, audio_path, language_code=language_code)
    
    if result.status in {"failed", "rate_limited"}:
        metrics.record_provider_error(result.solution_id)
        obs_logger.warning(
            "provider_pipeline_failed",
            solution_id=result.solution_id,
            status=result.status,
            runtime_seconds=result.total_runtime_seconds,
        )
    elif result.analysis and result.status == "completed":
        obs_logger.info(
            "provider_pipeline_completed",
            solution_id=result.solution_id,
            sentiment=result.analysis.sentiment,
            confidence=result.analysis.confidence,
            runtime_seconds=result.total_runtime_seconds,
        )
    
    return result

