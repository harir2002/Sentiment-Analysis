"""Derive client-facing recommended actions from analysis signals for financial services."""
from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import AnalysisResult


@dataclass(frozen=True)
class RecommendedActionPlan:
    recommended_action: str
    action_priority: str  # low|medium|high|urgent
    assigned_team: str  # customer_service|credit_team|fraud_prevention|compliance|operations|investment_services|documentation_team
    escalation_status: str  # none|standard|high|urgent|regulatory_escalation
    escalation_reason: str = ""


def _analysis_text(analysis: AnalysisResult) -> str:
    """Extract analysis text for pattern matching"""
    parts: list[str] = []
    if analysis.summary:
        parts.append(analysis.summary)
    if analysis.notes:
        parts.append(analysis.notes)
    if analysis.key_issues:
        parts.extend(analysis.key_issues)
    if analysis.action_items:
        parts.extend(analysis.action_items)
    if analysis.customer_issue:
        parts.append(analysis.customer_issue)
    return " ".join(parts).lower()


def derive_fintech_escalation(analysis: AnalysisResult) -> RecommendedActionPlan:
    """
    Derive escalation and routing for fintech customer support calls.
    
    Escalation priority (highest to lowest):
    1. Regulatory/Compliance issues → Compliance Team (URGENT)
    2. Fraud indicators → Fraud Prevention (URGENT)
    3. Critical complaints → Operations Manager (HIGH)
    4. KYC issues → Documentation Team (HIGH)
    5. Callback required → Operations (MEDIUM)
    6. Product-specific → Specialist teams (MEDIUM/LOW)
    7. Standard inquiry → Customer Service (LOW)
    """
    
    text = _analysis_text(analysis)
    sentiment = (analysis.sentiment or "neutral").strip().lower()
    confidence = float(analysis.confidence or 0.0)
    
    # PRIORITY 1: Regulatory & Compliance Issues
    if analysis.regulatory_flag or "regulatory" in text or "compliance" in text or analysis.kyc_status == "issue":
        return RecommendedActionPlan(
            recommended_action="Escalate to Compliance Team immediately for regulatory review and KYC verification",
            action_priority="urgent",
            assigned_team="compliance",
            escalation_status="regulatory_escalation",
            escalation_reason="Regulatory concern or KYC issue detected - immediate compliance review required"
        )
    
    # PRIORITY 2: Fraud Detection
    if analysis.fraud_indicators or analysis.fraud_risk_score > 0.7 or "fraud" in text or "suspicious" in text or "unauthorized" in text:
        return RecommendedActionPlan(
            recommended_action="Escalate to Fraud Prevention Team - suspicious activity pattern detected",
            action_priority="urgent",
            assigned_team="fraud_prevention",
            escalation_status="urgent",
            escalation_reason=f"Fraud risk detected (confidence: {analysis.fraud_risk_score:.2f}) - requires immediate investigation"
        )
    
    # PRIORITY 3: Critical Complaints (Negative sentiment + high severity)
    if analysis.complaint_severity == "critical" or (sentiment == "negative" and confidence > 0.8 and analysis.complaint_severity in ["major", "critical"]):
        return RecommendedActionPlan(
            recommended_action="Escalate to Operations Manager - Critical complaint requires immediate resolution",
            action_priority="urgent",
            assigned_team="operations",
            escalation_status="high",
            escalation_reason=f"Critical complaint (severity: {analysis.complaint_severity}) with negative sentiment - requires manager intervention"
        )
    
    # PRIORITY 4: KYC/Documentation Issues
    if analysis.kyc_status in ["pending", "issue"] or "kyc" in text or "document" in text or analysis.kyc_issues:
        return RecommendedActionPlan(
            recommended_action="Route to Documentation Team for KYC completion or verification",
            action_priority="high",
            assigned_team="documentation_team",
            escalation_status="high",
            escalation_reason=f"KYC status: {analysis.kyc_status} - requires documentation team for completion/resolution"
        )
    
    # PRIORITY 5: Callback Required
    if analysis.callback_required:
        priority = "high" if analysis.callback_priority in ["high", "urgent"] else "medium"
        return RecommendedActionPlan(
            recommended_action=f"Schedule callback with customer - Follow-up action required: {analysis.callback_reason}",
            action_priority=priority,
            assigned_team="operations",
            escalation_status="standard",
            escalation_reason=f"Customer callback required (priority: {analysis.callback_priority}) - {analysis.callback_reason}"
        )
    
    # PRIORITY 6: Product-Specific Routing
    if analysis.financial_product_type == "loan" or "loan" in text or "credit" in text:
        return RecommendedActionPlan(
            recommended_action="Route to Credit Team for loan-related inquiry, approval, or follow-up",
            action_priority="medium",
            assigned_team="credit_team",
            escalation_status="standard",
            escalation_reason="Loan product inquiry - requires credit team expertise"
        )
    
    if analysis.financial_product_type in ["investment", "nps", "mutual_fund"] or "investment" in text or "mutual fund" in text or "nps" in text:
        return RecommendedActionPlan(
            recommended_action="Route to Investment Services Team for product expertise and portfolio guidance",
            action_priority="medium",
            assigned_team="investment_services",
            escalation_status="standard",
            escalation_reason="Investment product inquiry - requires investment services specialist"
        )
    
    # PRIORITY 7: Major or Moderate Complaints
    if analysis.complaint_severity in ["major", "moderate"] or (sentiment == "negative" and analysis.complaint_severity != "none"):
        return RecommendedActionPlan(
            recommended_action="Create support ticket and assign to Customer Service for priority resolution",
            action_priority="high" if analysis.complaint_severity == "major" else "medium",
            assigned_team="customer_service",
            escalation_status="high" if analysis.complaint_severity == "major" else "standard",
            escalation_reason=f"Complaint severity: {analysis.complaint_severity} - requires priority attention"
        )
    
    # DEFAULT: Standard Customer Service Handling
    if sentiment == "positive" or (sentiment == "neutral" and analysis.complaint_severity in ["none", "minor"]):
        return RecommendedActionPlan(
            recommended_action="Standard customer service handling - resolve inquiry or provide information as needed",
            action_priority="low",
            assigned_team="customer_service",
            escalation_status="none",
            escalation_reason="Standard inquiry - no escalation needed"
        )
    
    # FALLBACK: Neutral or unclear
    return RecommendedActionPlan(
        recommended_action="Review call and determine appropriate follow-up action",
        action_priority="low" if confidence > 0.7 else "medium",
        assigned_team="customer_service",
        escalation_status="none" if confidence > 0.7 else "standard",
        escalation_reason="Manual review recommended due to unclear sentiment or low confidence" if confidence <= 0.7 else ""
    )


def enrich_analysis(analysis: AnalysisResult) -> AnalysisResult:
    """Enrich analysis with recommended actions and routing"""
    plan = derive_fintech_escalation(analysis)
    return analysis.model_copy(
        update={
            "recommended_action": plan.recommended_action,
            "action_priority": plan.action_priority,
            "assigned_team": plan.assigned_team,
            "escalation_status": plan.escalation_status,
            "escalation_level": plan.escalation_status,  # Map to new field
        }
    )

