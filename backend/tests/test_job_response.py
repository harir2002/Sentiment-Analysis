from datetime import datetime

from app.models.db_models import ComparisonJob
from app.models.schemas import JobStatus, ProviderResult, AnalysisResult, ComparisonRanking, RankingEntry, ScoreBreakdown


def _make_ranking(winner_id: str = "groq_whisper_sarvam_llm") -> dict:
    entry = RankingEntry(
        rank=1,
        solution_id=winner_id,
        label=winner_id,
        overall_score=80.0,
        score_breakdown=ScoreBreakdown(overall=80.0),
    )
    return ComparisonRanking(winner=entry, rankings=[entry]).model_dump()
from app.services.jobs import job_to_response


def _make_result(solution_id: str, status: str = "completed", stt_provider: str = "groq_stt") -> dict:
    return ProviderResult(
        solution_id=solution_id,
        label=solution_id,
        stt_provider=stt_provider,
        stt_model="whisper",
        llm_provider="groq",
        llm_model="test",
        status=status,
        transcript="hello",
        analysis=AnalysisResult(
            sentiment="neutral",
            summary="test",
            resolution_status="resolved",
            confidence=0.9,
        ),
        stt_runtime_seconds=1.0,
        llm_runtime_seconds=1.0,
        total_runtime_seconds=2.0,
        estimated_cost_usd=0.0,
        overall_score=80.0,
    ).model_dump()


def test_job_to_response_hides_results_until_all_providers_terminal():
    job = ComparisonJob(
        id="job-1",
        status=JobStatus.RUNNING.value,
        created_at=datetime.utcnow(),
        results=[
            _make_result("groq_whisper_sarvam_llm", "completed"),
            _make_result("groq_whisper_groq_gemma", "completed"),
            _make_result("sarvam_stt_sarvam_llm", "running", stt_provider="sarvam_stt"),
            _make_result("sarvam_stt_groq_gemma", "timed_out", stt_provider="sarvam_stt"),
        ],
        ranking=_make_ranking(),
    )

    response = job_to_response(job)

    assert response.results_ready is False
    assert response.results == []
    assert response.ranking is None
    assert response.pending_providers == 2
    assert response.aggregate_status == "running"
    assert response.provider_groups == {"open_source": [], "sarvam": []}


def test_job_to_response_shows_all_results_when_ready():
    job = ComparisonJob(
        id="job-2",
        status=JobStatus.COMPLETED.value,
        created_at=datetime.utcnow(),
        stt_language_code="ta-IN",
        results=[
            _make_result("groq_whisper_sarvam_llm", "completed"),
            _make_result("groq_whisper_groq_gemma", "completed"),
            _make_result("sarvam_stt_sarvam_llm", "failed", stt_provider="sarvam_stt"),
            _make_result("sarvam_stt_groq_gemma", "completed", stt_provider="sarvam_stt"),
        ],
        ranking=_make_ranking(),
    )

    response = job_to_response(job)

    assert response.results_ready is True
    assert len(response.results) == 4
    assert response.ranking is not None
    assert response.aggregate_status == "partial"
    assert len(response.provider_groups["open_source"]) == 2
    assert len(response.provider_groups["sarvam"]) == 2
    assert response.stt_language_code is None
    assert all(r.stt_language_code is None for r in response.results)
    assert response.ranking.recommendation_summary == ""
    assert response.ranking.winner.recommendation_reason == ""
