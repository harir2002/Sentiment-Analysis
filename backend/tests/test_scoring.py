from app.models.schemas import AnalysisResult, ProviderResult, SolutionOption
from app.services.scoring import build_ranking, estimate_cost, score_all_results


def _completed_result(solution_id: str, label: str, runtime: float, summary: str) -> ProviderResult:
    return ProviderResult(
        solution_id=solution_id,
        label=label,
        stt_provider="sarvam_stt",
        llm_provider="sarvam_llm",
        status="completed",
        transcript="Agent: Hello. Customer: I need help with my appointment booking today.",
        analysis=AnalysisResult(
            sentiment="neutral",
            key_issues=["appointment"],
            summary=summary,
            action_items=["Reschedule"],
            resolution_status="resolved",
            confidence=0.8,
        ),
        total_runtime_seconds=runtime,
    )


def test_estimate_cost_positive():
    cost = estimate_cost("sarvam_stt", "sarvam_llm", audio_minutes=2.0)
    assert cost > 0


def test_score_all_results_assigns_overall_score():
    results = [
        _completed_result("a", "A", 10.0, "Good summary one."),
        _completed_result("b", "B", 40.0, "Good summary two."),
    ]
    scored = score_all_results(results)
    assert all(r.overall_score > 0 for r in scored)
    assert all(r.scores for r in scored)
    assert all(r.estimated_cost_usd >= 0 for r in scored)


def test_build_ranking_orders_by_score():
    results = score_all_results(
        [
            _completed_result("slow", "Slow", 60.0, "Detailed summary for slow pipeline."),
            _completed_result("fast", "Fast", 5.0, "Detailed summary for fast pipeline."),
        ]
    )
    ranking = build_ranking(results)
    assert ranking["winner"]["solution_id"] == ranking["rankings"][0]["solution_id"]
    assert len(ranking["rankings"]) == 2
    assert ranking["recommendation_summary"].startswith("Recommended:")


def test_failed_result_scores_zero():
    failed = ProviderResult(
        solution_id=SolutionOption.SARVAM_SARVAM.value,
        label="Failed",
        stt_provider="sarvam_stt",
        llm_provider="sarvam_llm",
        status="failed",
        error="API error",
    )
    scored = score_all_results([failed])[0]
    assert scored.overall_score >= 0
    assert scored.scores.get("stt_quality", 0) == 0
