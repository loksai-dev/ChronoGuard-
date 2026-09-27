from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.graph.nodes import GraphContext
from app.graph.state import empty_state
from app.graph.workflow import build_graph, run_graph
from app.integrations.jev import JevClient
from app.integrations.neo4j import Neo4jStore
from app.integrations.openrouter import OpenRouterClient, OpenRouterError
from app.integrations.qdrant import QdrantStore
from app.models import IncidentCreate, IncidentRecord, IncidentStatus, RemediationAction, TimelineEvent
from app.observability.logging import audit
from app.observability.metrics import INCIDENTS_TOTAL, RESOLUTION_LATENCY
from app.remediation.executor import execute_actions
from app.remediation.verifier import verify_world
from app.remediation.world import WORLD
from app.services import STORE
from app.temporal.models import parse_utc


class Engine:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.neo4j: Neo4jStore | None
        self.qdrant: QdrantStore | None
        try:
            self.openrouter = OpenRouterClient(self.settings)
            self.jev = JevClient(self.settings, self.openrouter)
        except OpenRouterError:
            self.openrouter = None  # type: ignore[assignment]
            self.jev = None  # type: ignore[assignment]
        try:
            store = Neo4jStore(self.settings)
            self.neo4j = store if store.ping() else None
        except Exception:
            self.neo4j = None
        try:
            qstore = QdrantStore(self.settings)
            self.qdrant = qstore if qstore.ping() else None
        except Exception:
            self.qdrant = None
        if self.jev is None:
            self.compiled = None
            self.ctx = None
        else:
            self.ctx = GraphContext(self.jev, self.neo4j, self.qdrant, self.openrouter)
            self.compiled = build_graph(self.ctx)

    def health(self) -> dict[str, Any]:
        neo = "ok" if self.neo4j and self.neo4j.ping() else "unavailable"
        qdr = "ok" if self.qdrant and self.qdrant.ping() else "unavailable"
        status = "ok" if neo == "ok" and qdr == "ok" and self.jev is not None else "degraded"
        return {
            "status": status,
            "neo4j": neo,
            "qdrant": qdr,
            "openrouter_configured": self.jev is not None,
            "version": "1.0.0",
        }

    async def submit(self, payload: IncidentCreate) -> IncidentRecord:
        occurred = payload.occurred_at or parse_utc(self.settings.demo_incident_time)
        record = STORE.create(
            title=payload.title,
            description=payload.description,
            occurred_at=occurred,
        )
        audit("incident_received", incident_id=record.id, trace_id=record.trace_id)
        WORLD.reset_demo()
        if self.compiled is None or self.jev is None:
            record.error = "OPENROUTER_API_KEY missing; Jev cannot run. No fabricated triage was generated."
            record.status = IncidentStatus.DEGRADED
            STORE.save(record)
            INCIDENTS_TOTAL.labels(status=record.status.value).inc()
            return record
        state = empty_state(
            incident_id=record.id,
            trace_id=record.trace_id,
            title=record.title,
            description=record.description,
            occurred_at=occurred.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            logs=payload.logs,
            metrics=payload.metrics,
            max_retries=self.settings.max_retries,
        )
        started = datetime.now(timezone.utc)
        result = await run_graph(self.compiled, state)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        timings = dict(result.get("timings") or {})
        timings["total_resolution_time_ms"] = elapsed * 1000
        result["timings"] = timings
        RESOLUTION_LATENCY.observe(elapsed)
        record = STORE.apply_state(record.id, result)
        INCIDENTS_TOTAL.labels(status=record.status.value).inc()
        return record

    async def resume(self, incident_id: str, approval: dict[str, Any] | None = None) -> IncidentRecord:
        record = STORE.get(incident_id)
        if record is None:
            raise KeyError(incident_id)
        if self.ctx is None:
            raise RuntimeError("Graph is not available without OpenRouter/Jev")
        approval = approval or {}
        record.approval = {**(record.approval or {}), **approval}
        STORE.save(record)

        if record.status == IncidentStatus.AWAITING_APPROVAL and approval.get("approved"):
            return await self._execute_approved(record)

        if record.status in {IncidentStatus.HUMAN_REVIEW, IncidentStatus.FAILED} and record.triage:
            if record.triage.is_malicious:
                record.status = IncidentStatus.BLOCKED
                record.timeline.append(
                    TimelineEvent(node="blocked", message="Resume refused for malicious incident")
                )
                return STORE.save(record)
            from app.graph import nodes

            state = self._record_to_state(record)
            state["approval"] = record.approval
            state = nodes.investigation(state)
            dep = nodes.dependency_mapper(dict(state), self.ctx)
            temporal = nodes.temporal_state_reconstructor(dict(state), self.ctx)
            retrieval = nodes.historical_retrieval(dict(state), self.ctx)
            state["dependencies"] = dep.get("dependencies")
            state["temporal_state"] = temporal.get("temporal_state")
            state["retrieval"] = retrieval.get("retrieval")
            state = nodes.evidence_aggregator(state)
            state = await nodes.root_cause_analysis(state, self.ctx)
            state = nodes.remediation_planner(state)
            state = nodes.risk_gate(state)
            if any(item.get("requires_approval") for item in state.get("remediation_plan") or []) and not approval.get("approved"):
                state = nodes.human_approval(state)
            else:
                state = nodes.remediation_executor(state)
                state = nodes.verification(state)
                if (state.get("verification") or {}).get("verification_status") == "resolved":
                    state = nodes.resolved(state)
            return STORE.apply_state(record.id, state)

        if self.compiled is None:
            raise RuntimeError("Graph is not available")
        result = await run_graph(self.compiled, self._record_to_state(record))
        return STORE.apply_state(record.id, result)

    async def _execute_approved(self, record: IncidentRecord) -> IncidentRecord:
        from app.graph.nodes import append_event

        state = self._record_to_state(record)
        state["approval"] = record.approval
        plan = [RemediationAction.model_validate(item.model_dump()) for item in record.remediation_plan]
        results = execute_actions(plan, approved=True)
        state["executed_actions"] = results
        append_event(state, "remediation_executor", "Executed allowlisted actions after HITL approval")
        verification = verify_world("sales_daily")
        state["verification"] = verification
        append_event(state, "verification", "Post-approval verification", **verification)
        if verification["verification_status"] == "resolved":
            state["status"] = IncidentStatus.RESOLVED.value
            append_event(state, "resolved", "Incident resolved after verified remediation")
        else:
            state["status"] = IncidentStatus.FAILED.value
            append_event(state, "verification", "Verification did not confirm resolution")
        return STORE.apply_state(record.id, state)

    def _record_to_state(self, record: IncidentRecord) -> dict[str, Any]:
        occurred = record.occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return empty_state(
            incident_id=record.id,
            trace_id=record.trace_id,
            title=record.title,
            description=record.description,
            occurred_at=occurred,
            retry_count=record.retry_count,
            max_retries=self.settings.max_retries,
            triage=record.triage.model_dump(mode="json") if record.triage else {},
            dependencies=record.graph_snapshot,
            temporal_state=record.temporal_state,
            retrieval={"historical_incidents": record.historical_hits, "available": True},
            rca=record.rca.model_dump(mode="json") if record.rca else {},
            remediation_plan=[item.model_dump(mode="json") for item in record.remediation_plan],
            approval=record.approval or {},
            timeline=[e.model_dump(mode="json") for e in record.timeline],
            timings=record.metrics,
            status=record.status.value,
            current_node=record.current_node,
        )


ENGINE: Engine | None = None


def get_engine() -> Engine:
    global ENGINE
    if ENGINE is None:
        ENGINE = Engine()
    return ENGINE
