from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.graph.routing import append_event
from app.graph.state import AgentState
from app.integrations.jev import JevClient, apply_confidence_gate
from app.integrations.neo4j import Neo4jStore
from app.integrations.openrouter import OpenRouterClient, OpenRouterError
from app.integrations.qdrant import QdrantStore
from app.investigation.dependency_mapper import map_dependencies
from app.investigation.rca import build_rca
from app.investigation.retrieval import retrieve_evidence
from app.investigation.temporal_reconstruction import reconstruct_temporal_state
from app.models import IncidentStatus, TriageDecision
from app.observability.metrics import LANGGRAPH_LATENCY
from app.remediation.executor import execute_actions
from app.remediation.planner import plan_remediation, risk_requires_approval
from app.remediation.verifier import verify_world
from app.remediation.world import WORLD
from app.temporal.models import parse_utc


class GraphContext:
    def __init__(
        self,
        jev: JevClient,
        neo4j: Neo4jStore | None,
        qdrant: QdrantStore | None,
        chat: OpenRouterClient | None,
    ) -> None:
        self.jev = jev
        self.neo4j = neo4j
        self.qdrant = qdrant
        self.chat = chat
        self.settings = get_settings()


def incident_received(state: AgentState) -> AgentState:
    append_event(state, "incident_received", "Incident accepted for ChronoGuard processing")
    state["status"] = IncidentStatus.RECEIVED.value
    return state


async def jev_triage(state: AgentState, ctx: GraphContext) -> AgentState:
    append_event(state, "jev_triage", "Calling Jev via OpenRouter Decisions API")
    state["status"] = IncidentStatus.TRIAGING.value
    started = time.perf_counter()
    try:
        decision = await ctx.jev.triage(
            title=state["title"],
            description=state["description"],
            occurred_at=state.get("occurred_at"),
            logs=state.get("logs"),
            trace_id=state.get("trace_id"),
        )
        decision = apply_confidence_gate(decision, ctx.settings)
        state["triage"] = decision.model_dump(mode="json")
        timings = dict(state.get("timings") or {})
        timings["jev_latency_ms"] = decision.jev_latency_ms
        timings["openrouter_latency_ms"] = decision.openrouter_latency_ms
        state["timings"] = timings
        append_event(
            state,
            "jev_triage",
            "Jev returned a validated typed triage decision",
            category=decision.category.value,
            confidence=decision.confidence,
            route=decision.recommended_route.value,
        )
    except OpenRouterError as exc:
        state["error"] = f"Jev/OpenRouter failure: {exc}"
        state["status"] = IncidentStatus.DEGRADED.value
        state["triage"] = {}
        append_event(state, "jev_triage", "Jev call failed; refusing to invent a decision", error=str(exc))
    finally:
        LANGGRAPH_LATENCY.observe(time.perf_counter() - started)
    return state


def triage_router(state: AgentState) -> AgentState:
    append_event(state, "triage_router", "Applying confidence, malice, and HITL gates")
    return state


def blocked(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.BLOCKED.value
    state["pause"] = True
    append_event(state, "blocked", "Incident blocked because Jev classified it as malicious/suspicious")
    return state


def human_review(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.HUMAN_REVIEW.value
    state["pause"] = True
    append_event(state, "human_review", "Paused for human-in-the-loop review")
    return state


def investigation(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.INVESTIGATING.value
    state["observed"] = WORLD.snapshot()
    append_event(state, "investigation", "Starting parallel investigation fan-out")
    return state


def dependency_mapper(state: AgentState, ctx: GraphContext) -> AgentState:
    triage = state.get("triage") or {}
    component = triage.get("target_component")
    when = state.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    if ctx.neo4j is None:
        state["dependencies"] = {"available": False, "error": "Neo4j is not configured"}
    else:
        state["dependencies"] = map_dependencies(ctx.neo4j, component, when)
        if ctx.neo4j.ping() and component:
            try:
                ctx.neo4j.record_incident(state["incident_id"], state["title"], component, when)
            except Exception:
                pass
    append_event(state, "dependency_mapper", "Dependency mapping complete", available=state["dependencies"].get("available"))
    return state


def temporal_state_reconstructor(state: AgentState, ctx: GraphContext) -> AgentState:
    occurred = parse_utc(state.get("occurred_at") or datetime.now(timezone.utc).isoformat())
    valid_at = occurred.replace(hour=2, minute=0, second=0).isoformat().replace("+00:00", "Z")
    known_at = valid_at
    if ctx.neo4j is None:
        state["temporal_state"] = {"available": False, "error": "Neo4j is not configured"}
    else:
        state["temporal_state"] = reconstruct_temporal_state(ctx.neo4j, valid_at=valid_at, known_at=known_at)
    append_event(state, "temporal_state_reconstructor", "Bi-temporal reconstruction complete")
    return state


def historical_retrieval(state: AgentState, ctx: GraphContext) -> AgentState:
    text = f"{state.get('title','')} {state.get('description','')}"
    if ctx.qdrant is None:
        state["retrieval"] = {"available": False, "error": "Qdrant is not configured"}
    else:
        state["retrieval"] = retrieve_evidence(ctx.qdrant, text)
    append_event(state, "historical_retrieval", "Semantic retrieval complete", available=state["retrieval"].get("available"))
    return state


def evidence_aggregator(state: AgentState) -> AgentState:
    evidence: list[dict[str, Any]] = []
    for bucket in (state.get("retrieval") or {}).values():
        if isinstance(bucket, list):
            evidence.extend(bucket)
    state["evidence"] = evidence
    append_event(state, "evidence_aggregator", "Evidence package assembled")
    return state


async def root_cause_analysis(state: AgentState, ctx: GraphContext) -> AgentState:
    triage = TriageDecision.model_validate(state["triage"]) if state.get("triage") else None
    if triage is None:
        state["error"] = "Cannot run RCA without a validated Jev triage decision"
        state["status"] = IncidentStatus.DEGRADED.value
        return state
    rca = await build_rca(
        triage=triage,
        incident_text=state["description"],
        dependencies=state.get("dependencies") or {},
        temporal=state.get("temporal_state") or {},
        retrieval=state.get("retrieval") or {},
        observed=state.get("observed") or {},
        chat=ctx.chat,
        chat_model=ctx.settings.openrouter_chat_model,
    )
    state["rca"] = rca.model_dump(mode="json")
    append_event(state, "root_cause_analysis", "Hypothesis generated from evidence (not confirmed)")
    return state


def remediation_planner(state: AgentState) -> AgentState:
    triage = TriageDecision.model_validate(state["triage"])
    rca = None
    if state.get("rca"):
        from app.models import RootCausePackage

        rca = RootCausePackage.model_validate(state["rca"])
    plan = plan_remediation(triage, rca)
    state["remediation_plan"] = [item.model_dump(mode="json") for item in plan]
    append_event(state, "remediation_planner", "Remediation plan generated from allowlisted actions")
    return state


def risk_gate(state: AgentState) -> AgentState:
    from app.models import RemediationAction

    triage = TriageDecision.model_validate(state["triage"])
    plan = [RemediationAction.model_validate(item) for item in state.get("remediation_plan") or []]
    if risk_requires_approval(plan, triage) and not (state.get("approval") or {}).get("approved"):
        append_event(state, "risk_gate", "High-risk or HITL plan; waiting for approval")
    else:
        append_event(state, "risk_gate", "Risk gate passed for allowlisted simulated actions")
    return state


def human_approval(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.AWAITING_APPROVAL.value
    state["pause"] = True
    append_event(state, "human_approval", "Waiting for human approval before execution")
    return state


def remediation_executor(state: AgentState) -> AgentState:
    from app.models import RemediationAction

    state["status"] = IncidentStatus.REMEDIATING.value
    plan = [RemediationAction.model_validate(item) for item in state.get("remediation_plan") or []]
    approved = bool((state.get("approval") or {}).get("approved")) or not any(p.requires_approval for p in plan)
    results = execute_actions(plan, approved=approved)
    state["executed_actions"] = results
    append_event(state, "remediation_executor", "Executed allowlisted simulated remediation")
    return state


def verification(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.VERIFYING.value
    result = verify_world("sales_daily")
    state["verification"] = result
    append_event(state, "verification", "Verification evaluated simulated world state", **result)
    return state


def resolved(state: AgentState) -> AgentState:
    state["status"] = IncidentStatus.RESOLVED.value
    state["pause"] = True
    append_event(state, "resolved", "Incident marked resolved after successful verification")
    return state


def retry_investigation(state: AgentState) -> AgentState:
    state["retry_count"] = int(state.get("retry_count") or 0) + 1
    state["pause"] = False
    append_event(state, "retry_investigation", "Verification failed; retrying investigation", retry=state["retry_count"])
    return state
