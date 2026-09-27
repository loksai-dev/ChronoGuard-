from __future__ import annotations

from typing import Any, TypedDict

from app.models import IncidentStatus, RemediationAction, RootCausePackage, TriageDecision, VerificationStatus


class AgentState(TypedDict, total=False):
    incident_id: str
    trace_id: str
    title: str
    description: str
    occurred_at: str
    logs: list[str]
    metrics: dict[str, Any]
    current_node: str
    status: str
    retry_count: int
    max_retries: int
    triage: dict[str, Any]
    dependencies: dict[str, Any]
    temporal_state: dict[str, Any]
    retrieval: dict[str, Any]
    observed: dict[str, Any]
    evidence: list[dict[str, Any]]
    rca: dict[str, Any]
    remediation_plan: list[dict[str, Any]]
    executed_actions: list[dict[str, Any]]
    verification: dict[str, Any]
    approval: dict[str, Any]
    error: str | None
    pause: bool
    timeline: list[dict[str, Any]]
    timings: dict[str, Any]


def empty_state(**kwargs: Any) -> AgentState:
    state: AgentState = {
        "incident_id": "",
        "trace_id": "",
        "title": "",
        "description": "",
        "occurred_at": "",
        "logs": [],
        "metrics": {},
        "current_node": "incident_received",
        "status": IncidentStatus.RECEIVED.value,
        "retry_count": 0,
        "max_retries": 3,
        "triage": {},
        "dependencies": {},
        "temporal_state": {},
        "retrieval": {},
        "observed": {},
        "evidence": [],
        "rca": {},
        "remediation_plan": [],
        "executed_actions": [],
        "verification": {},
        "approval": {},
        "error": None,
        "pause": False,
        "timeline": [],
        "timings": {},
    }
    state.update(kwargs)
    return state
