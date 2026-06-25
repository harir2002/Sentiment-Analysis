"""Shared report structure for client-ready exports."""

from __future__ import annotations



from dataclasses import dataclass, field

from datetime import datetime



from app.models.schemas import JobResponse, ProviderResult, SolutionOption, SOLUTION_LABELS

from app.providers.registry import SOLUTION_CONFIG

from app.services.recommended_action import enrich_analysis



PROJECT_NAME = "Dr. Mohan's Call Analytics Comparison"

REPORT_TITLE = "STT + LLM Pipeline Comparison Report"

REPORT_VERSION = "1.0.0"

PREPARED_BY = "Call Analytics Lab"

EXPECTED_SOLUTION_COUNT = 4



SOLUTION_ORDER = [

    SolutionOption.SARVAM_SARVAM,

    SolutionOption.SARVAM_GROQ,

    SolutionOption.GROQ_SARVAM,

    SolutionOption.GROQ_GROQ,

]



COMPARISON_COLUMNS = [

    "Solution",

    "Status",

    "Sentiment",

    "Confidence",

    "Summary",

    "Key Issues",

    "Score",

    "Recommended Action",

]



TEST_CASE_COLUMNS = [

    "Test ID",

    "Pipeline",

    "Transcript",

    "Sentiment",

    "Expected Result",

    "Summary",

    "Confidence Score",

    "Status",

    "Notes",

]



EXPECTED_RESULT = "Structured call analysis with sentiment, summary, and resolution status"





@dataclass

class ReportHeader:

    project_name: str

    report_title: str

    date: str

    version: str

    prepared_by: str

    job_id: str

    audio_filename: str

    call_reference: str





@dataclass

class ExecutiveSummary:

    total_test_cases: int

    passed_count: int

    failed_count: int

    neutral_count: int

    best_solution: str

    comparison_note: str





@dataclass

class ComparisonRow:

    solution: str

    status: str

    sentiment: str

    confidence: str

    summary: str

    key_issues: str

    score: str

    recommended_action: str



    def as_list(self) -> list[str]:

        return [

            self.solution,

            self.status,

            self.sentiment,

            self.confidence,

            self.summary,

            self.key_issues,

            self.score,

            self.recommended_action,

        ]





@dataclass

class TestCaseRow:

    test_id: str

    pipeline: str

    transcript: str

    sentiment: str

    expected_result: str

    summary: str

    confidence_score: str

    status: str

    notes: str



    def as_list(self) -> list[str]:

        return [

            self.test_id,

            self.pipeline,

            self.transcript,

            self.sentiment,

            self.expected_result,

            self.summary,

            self.confidence_score,

            self.status,

            self.notes,

        ]





@dataclass

class SolutionObservation:

    solution: str

    status: str

    sentiment: str

    confidence: str

    resolution_status: str

    summary: str

    key_issues: str

    action_items: str

    notes: str

    transcript: str

    score: str

    error: str

    recommended_action: str

    action_priority: str

    assigned_team: str

    escalation_status: str





@dataclass

class FinalComparison:

    winner: str

    winner_score: str

    rankings: list[str] = field(default_factory=list)





@dataclass

class ComparisonReport:

    header: ReportHeader

    summary: ExecutiveSummary

    comparison_rows: list[ComparisonRow] = field(default_factory=list)

    test_cases: list[TestCaseRow] = field(default_factory=list)

    observations: list[SolutionObservation] = field(default_factory=list)

    final_comparison: FinalComparison | None = None





def _row_status(result: ProviderResult) -> str:

    if result.status == "completed":

        sentiment = (result.analysis.sentiment or "").lower()

        if sentiment == "neutral":

            return "Neutral"

        return "Pass"

    if result.status in {"failed", "rate_limited"}:

        return "Fail"

    return "Neutral"





def _normalize_text(value: str | None) -> str:

    return " ".join((value or "").split())





def _placeholder_result(solution: SolutionOption) -> ProviderResult:

    stt_name, llm_name = SOLUTION_CONFIG[solution]

    return ProviderResult(

        solution_id=solution.value,

        label=SOLUTION_LABELS[solution],

        stt_provider=stt_name,

        llm_provider=llm_name,

        status="failed",

        error="No result returned for this pipeline",

    )





def order_solution_results(results: list[ProviderResult]) -> list[ProviderResult]:

    by_id = {r.solution_id: r for r in results}

    ordered: list[ProviderResult] = []

    for solution in SOLUTION_ORDER:

        ordered.append(by_id.get(solution.value) or _placeholder_result(solution))

    return ordered





def _build_comparison_row(result: ProviderResult) -> ComparisonRow:

    if result.status == "completed":

        issues = "; ".join(result.analysis.key_issues) if result.analysis.key_issues else "—"

        analysis = enrich_analysis(result.analysis)

        return ComparisonRow(

            solution=_normalize_text(result.label) or "—",

            status="Completed",

            sentiment=_normalize_text(analysis.sentiment) or "—",

            confidence=f"{analysis.confidence * 100:.0f}%",

            summary=_normalize_text(analysis.summary) or "—",

            key_issues=_normalize_text(issues) or "—",

            score=f"{result.overall_score:.2f}",

            recommended_action=_normalize_text(analysis.recommended_action) or "—",

        )



    status_label = (result.status or "unknown").replace("_", " ").title()

    return ComparisonRow(

        solution=_normalize_text(result.label) or "—",

        status=status_label,

        sentiment="—",

        confidence="—",

        summary=_normalize_text(result.error or result.status_message or "No result") or "—",

        key_issues="—",

        score="—",

        recommended_action="—",

    )





def _build_test_row(index: int, result: ProviderResult) -> TestCaseRow:

    transcript = _normalize_text(result.transcript) or "—"



    if result.status == "completed":

        summary = _normalize_text(result.analysis.summary) or "—"

        notes = _normalize_text(result.analysis.notes)

        if result.analysis.key_issues:

            issues = "; ".join(result.analysis.key_issues)

            notes = f"{notes} | Issues: {issues}".strip(" |")

        confidence = f"{result.analysis.confidence * 100:.0f}%"

        sentiment = _normalize_text(result.analysis.sentiment) or "—"

    else:

        summary = _normalize_text(result.error or result.status_message or "No result") or "—"

        notes = _normalize_text(result.parsing_error or result.status_message)

        confidence = "—"

        sentiment = "—"



    return TestCaseRow(

        test_id=f"TC-{index:03d}",

        pipeline=_normalize_text(result.label) or "—",

        transcript=transcript,

        sentiment=sentiment,

        expected_result=EXPECTED_RESULT,

        summary=summary,

        confidence_score=confidence,

        status=_row_status(result),

        notes=notes or "—",

    )





def _build_observation(result: ProviderResult) -> SolutionObservation:

    if result.status == "completed":

        analysis = enrich_analysis(result.analysis)

        return SolutionObservation(

            solution=_normalize_text(result.label) or "—",

            status="Completed",

            sentiment=_normalize_text(analysis.sentiment) or "—",

            confidence=f"{analysis.confidence * 100:.0f}%",

            resolution_status=_normalize_text(analysis.resolution_status) or "—",

            summary=_normalize_text(analysis.summary) or "—",

            key_issues="; ".join(analysis.key_issues) if analysis.key_issues else "—",

            action_items="; ".join(analysis.action_items) if analysis.action_items else "—",

            notes=_normalize_text(analysis.notes) or "—",

            transcript=_normalize_text(result.transcript) or "—",

            score=f"{result.overall_score:.2f}",

            error="—",

            recommended_action=_normalize_text(analysis.recommended_action) or "—",

            action_priority=_normalize_text(analysis.action_priority) or "—",

            assigned_team=_normalize_text(analysis.assigned_team) or "—",

            escalation_status=_normalize_text(analysis.escalation_status) or "—",

        )



    status_label = (result.status or "unknown").replace("_", " ").title()

    return SolutionObservation(

        solution=_normalize_text(result.label) or "—",

        status=status_label,

        sentiment="—",

        confidence="—",

        resolution_status="—",

        summary="—",

        key_issues="—",

        action_items="—",

        notes="—",

        transcript=_normalize_text(result.transcript) or "—",

        score="—",

        error=_normalize_text(result.error or result.status_message or "No result") or "—",

        recommended_action="—",

        action_priority="—",

        assigned_team="—",

        escalation_status="—",

    )





def _build_final_comparison(job: JobResponse) -> FinalComparison | None:

    if not job.ranking:

        return None



    winner_label = "—"

    winner_score = "—"

    if job.ranking.winner:

        winner_label = job.ranking.winner.label

        winner_score = f"{job.ranking.winner.overall_score:.2f}"



    rankings = [

        f"#{entry.rank} {entry.label} — score {entry.overall_score:.2f}"

        for entry in job.ranking.rankings

    ]

    return FinalComparison(winner=winner_label, winner_score=winner_score, rankings=rankings)





def build_comparison_report(job: JobResponse) -> ComparisonReport:

    results = order_solution_results(job.results or [])



    passed = sum(1 for r in results if _row_status(r) == "Pass")

    failed = sum(1 for r in results if _row_status(r) == "Fail")

    neutral = sum(1 for r in results if _row_status(r) == "Neutral")



    winner = "—"

    if job.ranking and job.ranking.winner:

        winner = job.ranking.winner.label



    report_date = job.completed_at or job.created_at or datetime.utcnow()

    date_str = report_date.strftime("%d %B %Y") if report_date else datetime.utcnow().strftime("%d %B %Y")



    header = ReportHeader(

        project_name=PROJECT_NAME,

        report_title=REPORT_TITLE,

        date=date_str,

        version=REPORT_VERSION,

        prepared_by=PREPARED_BY,

        job_id=job.job_id,

        audio_filename=job.audio_filename or "—",

        call_reference=job.call_reference or "—",

    )



    summary = ExecutiveSummary(

        total_test_cases=len(results),

        passed_count=passed,

        failed_count=failed,

        neutral_count=neutral,

        best_solution=winner,

        comparison_note=(

            f"Side-by-side comparison across {EXPECTED_SOLUTION_COUNT} STT + LLM pipelines. "

            "All pipelines are included in this report."

        ),

    )



    comparison_rows = [_build_comparison_row(r) for r in results]

    test_cases = [_build_test_row(i + 1, r) for i, r in enumerate(results)]

    observations = [_build_observation(r) for r in results]

    final_comparison = _build_final_comparison(job)



    return ComparisonReport(

        header=header,

        summary=summary,

        comparison_rows=comparison_rows,

        test_cases=test_cases,

        observations=observations,

        final_comparison=final_comparison,

    )

