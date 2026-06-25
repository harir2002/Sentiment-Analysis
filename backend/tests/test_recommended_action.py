"""Tests for recommended action mapping."""
from app.models.schemas import AnalysisResult
from app.services.recommended_action import derive_recommended_action, enrich_analysis


def test_positive_sentiment_no_action():
    plan = derive_recommended_action(
        AnalysisResult(sentiment="positive", confidence=0.9, summary="Customer was satisfied.")
    )
    assert "No action needed" in plan.recommended_action
    assert plan.action_priority == "Low"
    assert plan.escalation_status == "None"


def test_negative_sentiment_escalates():
    plan = derive_recommended_action(
        AnalysisResult(
            sentiment="negative",
            confidence=0.85,
            summary="Customer was unhappy with billing.",
            key_issues=["billing error"],
        )
    )
    assert "Escalate" in plan.recommended_action
    assert plan.action_priority == "High"
    assert plan.escalation_status == "Escalated"


def test_neutral_sentiment_monitor():
    plan = derive_recommended_action(
        AnalysisResult(sentiment="neutral", confidence=0.8, summary="Routine inquiry.")
    )
    assert "Monitor" in plan.recommended_action
    assert plan.action_priority == "Low"


def test_medical_concern_critical():
    plan = derive_recommended_action(
        AnalysisResult(
            sentiment="negative",
            confidence=0.9,
            summary="Patient reported severe pain and needs urgent doctor callback.",
            key_issues=["medical concern"],
        )
    )
    assert plan.action_priority == "Critical"
    assert plan.assigned_team == "Clinical Care Team"
    assert plan.escalation_status == "Critical"


def test_appointment_issue_callback():
    plan = derive_recommended_action(
        AnalysisResult(
            sentiment="negative",
            confidence=0.88,
            summary="Appointment was delayed again.",
            key_issues=["appointment delay"],
        )
    )
    assert "callback" in plan.recommended_action.lower()
    assert plan.assigned_team == "Appointment Services"


def test_repeated_issues_complaint_ticket():
    plan = derive_recommended_action(
        AnalysisResult(
            sentiment="negative",
            confidence=0.9,
            summary="Customer complained about repeated service failures.",
            key_issues=["missed callback", "unresolved billing"],
        )
    )
    assert "complaint ticket" in plan.recommended_action.lower()
    assert plan.assigned_team == "Complaints Desk"


def test_low_confidence_adds_manual_review():
    plan = derive_recommended_action(
        AnalysisResult(sentiment="positive", confidence=0.4, summary="Short call.")
    )
    assert "Manual review recommended" in plan.recommended_action


def test_enrich_analysis_populates_fields():
    enriched = enrich_analysis(AnalysisResult(sentiment="neutral", confidence=0.8))
    assert enriched.recommended_action
    assert enriched.action_priority
    assert enriched.assigned_team
    assert enriched.escalation_status
