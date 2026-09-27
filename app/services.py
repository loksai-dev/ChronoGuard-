from __future__ import annotations

from threading import Lock
from typing import Any
from uuid import uuid4

from app.models import IncidentRecord, IncidentStatus, TimelineEvent, utc_now


class IncidentStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: dict[str, IncidentRecord] = {}

    def create(self, title: str, description: str, occurred_at: Any, **kwargs: Any) -> IncidentRecord:
        incident_id = str(uuid4())
        record = IncidentRecord(
            id=incident_id,
            trace_id=str(uuid4()),
            title=title,
            description=description,
            occurred_at=occurred_at or utc_now(),
            received_at=utc_now(),
            status=IncidentStatus.RECEIVED,
            current_node="incident_received",
            **kwargs,
        )
        with self._lock:
            self._items[incident_id] = record
        return record

    def get(self, incident_id: str) -> IncidentRecord | None:
        with self._lock:
            return self._items.get(incident_id)

    def list(self) -> list[IncidentRecord]:
        with self._lock:
            return list(self._items.values())

    def save(self, record: IncidentRecord) -> IncidentRecord:
        with self._lock:
            self._items[record.id] = record
        return record

    def apply_state(self, incident_id: str, state: dict[str, Any]) -> IncidentRecord:
        record = self.get(incident_id)
        if record is None:
            raise KeyError(incident_id)
        record.status = IncidentStatus(state.get("status") or record.status)
        record.current_node = state.get("current_node") or record.current_node
        record.retry_count = int(state.get("retry_count") or 0)
        if state.get("triage"):
            from app.models import TriageDecision

            record.triage = TriageDecision.model_validate(state["triage"])
        record.graph_snapshot = state.get("dependencies") or record.graph_snapshot
        record.temporal_state = state.get("temporal_state") or record.temporal_state
        record.historical_hits = (state.get("retrieval") or {}).get("historical_incidents") or record.historical_hits
        if state.get("rca"):
            from app.models import RootCausePackage

            record.rca = RootCausePackage.model_validate(state["rca"])
        if state.get("remediation_plan"):
            from app.models import RemediationAction

            record.remediation_plan = [RemediationAction.model_validate(item) for item in state["remediation_plan"]]
        record.executed_actions = state.get("executed_actions") or record.executed_actions
        verification = state.get("verification") or {}
        if verification.get("verification_status"):
            from app.models import VerificationStatus

            record.verification_status = VerificationStatus(verification["verification_status"])
            record.verification_evidence = verification
        record.error = state.get("error")
        record.metrics = state.get("timings") or record.metrics
        record.approval = state.get("approval") or record.approval
        record.timeline = [
            TimelineEvent.model_validate(item) for item in state.get("timeline") or [e.model_dump() for e in record.timeline]
        ]
        return self.save(record)


STORE = IncidentStore()
