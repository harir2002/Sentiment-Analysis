from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    RATE_LIMITED = "rate_limited"
    TIMED_OUT = "timed_out"


class SolutionOption(str, Enum):
    SARVAM_SARVAM = "sarvam_stt_sarvam_llm"
    SARVAM_GROQ = "sarvam_stt_groq_gemma"
    GROQ_SARVAM = "groq_whisper_sarvam_llm"
    GROQ_GROQ = "groq_whisper_groq_gemma"


SOLUTION_LABELS = {
    SolutionOption.SARVAM_SARVAM: "Sarvam STT + Sarvam LLM",
    SolutionOption.SARVAM_GROQ: "Sarvam STT + Groq Gemma 4 26B A4B",
    SolutionOption.GROQ_SARVAM: "Groq Whisper + Sarvam LLM",
    SolutionOption.GROQ_GROQ: "Groq Whisper + Groq Gemma 4 26B A4B",
}


class AnalysisResult(BaseModel):
    # Primary sentiment (backward compatible)
    sentiment: str = ""  # positive|neutral|negative|mixed
    
    # FINTECH: Customer satisfaction level
    customer_satisfaction: str = ""  # very_satisfied|satisfied|neutral|dissatisfied|very_dissatisfied
    
    # FINTECH: Complaint severity
    complaint_severity: str = "none"  # none|minor|moderate|major|critical
    
    # FINTECH: Financial product type
    financial_product_type: str = ""  # account_opening|savings|checking|credit_card|loan|insurance|investment|nps|other
    
    # FINTECH: Customer issue description
    customer_issue: str = ""  # what the customer called about
    
    # FINTECH: Transaction details
    transaction_amount_mentioned: Optional[float] = None
    transaction_type: str = ""  # deposit|withdrawal|transfer|purchase|payment|etc
    
    # FINTECH: Regulatory & compliance
    regulatory_flag: bool = False  # RBI/SEBI/IRDA mentioned
    regulatory_mentions: list[str] = Field(default_factory=list)  # specific regulations mentioned
    kyc_status: str = ""  # complete|pending|issue
    kyc_issues: list[str] = Field(default_factory=list)  # specific KYC problems
    
    # FINTECH: Risk indicators
    fraud_indicators: bool = False  # suspicious activity detected
    fraud_risk_score: float = 0.0  # 0.0-1.0
    
    # FINTECH: Operational requirements
    callback_required: bool = False
    callback_reason: str = ""
    callback_priority: str = ""  # low|medium|high|urgent
    
    # FINTECH: Escalation specifics
    escalation_level: str = "none"  # none|standard|high|urgent|regulatory_escalation
    escalation_reason: str = ""
    escalation_risk: str = "low"  # low|medium|high (for CRM integration)
    
    # Existing fields (maintained for backward compatibility)
    issue_type: str = ""  # transaction_issue|service_delay|complaint|inquiry|escalation|other
    key_issues: list[str] = Field(default_factory=list)
    summary: str = ""
    action_items: list[str] = Field(default_factory=list)
    resolution_status: str = ""  # resolved|partially_resolved|unresolved|escalated
    confidence: float = 0.0
    notes: str = ""
    recommended_action: str = ""
    action_priority: str = ""
    assigned_team: str = ""
    escalation_status: str = ""


class ProviderResult(BaseModel):
    solution_id: str
    label: str
    stt_provider: str
    llm_provider: str
    stt_model: str = ""
    llm_model: str = ""
    status: str = "pending"
    transcript: str = ""
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    stt_runtime_seconds: float = 0.0
    llm_runtime_seconds: float = 0.0
    total_runtime_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    error: str | None = None
    parsing_error: str | None = None
    raw_llm_response: str | None = None
    raw_stt_response: str | None = None
    retry_count: int = 0
    sarvam_batch_job_id: str | None = None
    status_message: str | None = None
    stt_language_code: str | None = None
    language_mismatch_warning: str | None = None
    detected_script: str | None = None
    whisper_detected_language: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    path: str
    metadata: dict = Field(default_factory=dict)


class UploadItemResult(BaseModel):
    file_id: str | None = None
    filename: str
    path: str | None = None
    metadata: dict = Field(default_factory=dict)
    success: bool
    error: str | None = None


class BatchUploadResponse(BaseModel):
    uploaded: list[UploadItemResult] = Field(default_factory=list)
    failed: list[UploadItemResult] = Field(default_factory=list)
    total: int = 0
    success_count: int = 0
    failed_count: int = 0


class RunComparisonRequest(BaseModel):
    file_id: str
    call_reference: str | None = None


class RetryProvidersRequest(BaseModel):
    solution_ids: list[str] | None = None


class ErrorResponse(BaseModel):
    detail: str
    provider: str | None = None
    status_code: int | None = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime | None = None
    completed_at: datetime | None = None
    total_runtime_seconds: float | None = None
    call_reference: str | None = None
    stt_language_code: str | None = None
    audio_filename: str | None = None
    result: AnalysisResult | None = None
    error: str | None = None
    pending_providers: int = 0
    results_ready: bool = False
    aggregate_status: str = "running"
    status_message: str = ""  # Human-readable status like "25% - Transcribing..."


class CallListItem(BaseModel):
    job_id: str
    status: JobStatus
    audio_filename: str | None = None
    call_reference: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    aggregate_status: str = "running"
    results_ready: bool = False


class CallsListResponse(BaseModel):
    calls: list[CallListItem] = Field(default_factory=list)
    total: int = 0


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "1.0.0"
    providers: dict[str, bool] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
