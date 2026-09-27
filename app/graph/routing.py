from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.graph.state import AgentState
from app.models import IncidentStatus, RecommendedRoute


def append_event(state: AgentState, node: str, message: str, **data: object) -> None:
    events = list(state.get("timeline") or [])
    events.append(
        {
            "id": str(uuid4()),
            "at": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "message": message,
            "data": data,
        }
    )
    state["timeline"] = events
    state["current_node"] = node


def route_after_triage(state: AgentState) -> str:
    triage = state.get("triage") or {}
    route = triage.get("recommended_route")
    if route == RecommendedRoute.BLOCKED.value or triage.get("is_malicious"):
        return "blocked"
    if route == RecommendedRoute.HUMAN_REVIEW.value or triage.get("requires_human_review"):
        if state.get("approval", {}).get("investigate_anyway"):
            return "investigation"
        return "human_review"
    return "investigation"


def route_after_risk(state: AgentState) -> str:
    if state.get("error"):
        return "human_review"
    plan = state.get("remediation_plan") or []
    needs = any(item.get("requires_approval") for item in plan)
    approved = bool((state.get("approval") or {}).get("approved"))
    if needs and not approved:
        return "human_approval"
    return "remediation_executor"


def route_after_verification(state: AgentState) -> str:
    verification = state.get("verification") or {}
    status = verification.get("verification_status")
    if status == "resolved":
        return "resolved"
    retries = int(state.get("retry_count") or 0)
    max_retries = int(state.get("max_retries") or 3)
    if retries < max_retries and status in {"failed", "inconclusive"}:
        return "retry_investigation"
    return "human_review"
