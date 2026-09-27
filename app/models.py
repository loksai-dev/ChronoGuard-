from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentCategory(str, Enum):
    DATABASE = "database"
    PIPELINE = "pipeline"
    INFRASTRUCTURE = "infrastructure"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    APPLICATION = "application"
    SECURITY = "security"
    UNKNOWN = "unknown"


class RecommendedRoute(str, Enum):
    INVESTIGATE = "investigate"
    BLOCKED = "blocked"
    HUMAN_REVIEW = "human_review"


class ReasonCode(str, Enum):
    PIPELINE_TIMEOUT = "pipeline_timeout"
    DEPENDENCY_FAILURE = "dependency_failure"
    DEPLOYMENT_REGRESSION = "deployment_regression"
    AUTH_ANOMALY = "auth_anomaly"
    NETWORK_PARTITION = "network_partition"
    RESOURCE_SATURATION = "resource_saturation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    INSUFFICIENT_SIGNAL = "insufficient_signal"
    DATA_QUALITY = "data_quality"
    UNKNOWN = "unknown"


class TargetComponent(str, Enum):
    SALES_DAILY = "sales_daily"
    SALES_FACT_DETAIL = "sales_fact_detail"
    ATHENA = "athena"
    QUERY_SERVICE = "query_service"
    AIRFLOW = "airflow"
    UNKNOWN = "unknown"
    NONE = "none"


class RemediationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentStatus(str, Enum):
    RECEIVED = "received"
    TRIAGING = "triaging"
    BLOCKED = "blocked"
    HUMAN_REVIEW = "human_review"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    FAILED = "failed"
    DEGRADED = "degraded"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    RESOLVED = "resolved"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    PENDING = "pending"


class EvidenceKind(str, Enum):
    OBSERVED_FACT = "OBSERVED_FACT"
    INFERRED_FACT = "INFERRED_FACT"
    HYPOTHESIS = "HYPOTHESIS"


class AllowedRemediation(str, Enum):
    RESTART_SERVICE = "restart_service"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    RERUN_PIPELINE = "rerun_pipeline"
    INVALIDATE_CACHE = "invalidate_cache"
    PAUSE_PIPELINE = "pause_pipeline"


class TriageDecision(BaseModel):
    category: IncidentCategory
    severity: int = Field(ge=1, le=10)
    is_malicious: bool
    target_component: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool
    recommended_route: RecommendedRoute
    reason_code: ReasonCode
    remediation_risk: RemediationRisk = RemediationRisk.LOW
    malicious_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_information: bool = False
    jev_raw_answers: dict[str, Any] = Field(default_factory=dict)
    jev_model: str | None = None
    jev_latency_ms: float | None = None
    openrouter_latency_ms: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_component", mode="before")
    @classmethod
    def empty_component_to_none(cls, value: Any) -> Any:
        if value in ("", "none", "unknown", None):
            return None if value in ("", "none") else value
        return value


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=8, max_length=8000)
    occurred_at: datetime | None = None
    source: str = "manual"
    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=2000)


class RejectionRequest(BaseModel):
    rejected_by: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=2000)


class EvidenceItem(BaseModel):
    id: str
    kind: EvidenceKind
    source: str
    summary: str
    score: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RemediationAction(BaseModel):
    action: AllowedRemediation
    target: str
    risk_level: RemediationRisk
    reason: str
    expected_effect: str
    rollback_action: str
    requires_approval: bool


class RootCausePackage(BaseModel):
    root_cause_hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceItem] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    recommended_action: str
    disclaimer: str = "This is a hypothesis, not a confirmed root cause."


class TimelineEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    at: datetime = Field(default_factory=utc_now)
    node: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class IncidentRecord(BaseModel):
    id: str
    trace_id: str
    title: str
    description: str
    occurred_at: datetime
    received_at: datetime
    status: IncidentStatus
    current_node: str
    retry_count: int = 0
    triage: TriageDecision | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    rca: RootCausePackage | None = None
    remediation_plan: list[RemediationAction] = Field(default_factory=list)
    executed_actions: list[dict[str, Any]] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_evidence: dict[str, Any] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    graph_snapshot: dict[str, Any] = Field(default_factory=dict)
    temporal_state: dict[str, Any] = Field(default_factory=dict)
    historical_hits: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    approval: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    neo4j: str
    qdrant: str
    openrouter_configured: bool
    version: str
