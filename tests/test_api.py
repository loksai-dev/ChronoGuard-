from fastapi.testclient import TestClient

from app.investigation.dependency_mapper import map_dependencies
from app.investigation.retrieval import retrieve_evidence
from app.integrations.neo4j import Neo4jUnavailable
from app.integrations.qdrant import QdrantUnavailable
from app.main import app
from app.models import IncidentStatus, utc_now
from app.services import STORE


class FakeStore:
    def incident_graph(self, *args, **kwargs):
        raise Neo4jUnavailable("down")

    def dependencies_valid_at(self, *args, **kwargs):
        raise Neo4jUnavailable("down")


class FakeQdrant:
    def search(self, *args, **kwargs):
        raise QdrantUnavailable("down")


def test_neo4j_unavailable_is_degraded_not_silent():
    result = map_dependencies(FakeStore(), "sales_daily", "2026-09-27T02:14:00Z")  # type: ignore[arg-type]
    assert result["available"] is False
    assert "down" in result["error"]


def test_qdrant_unavailable_is_degraded_not_silent():
    result = retrieve_evidence(FakeQdrant(), "athena timeout")  # type: ignore[arg-type]
    assert result["available"] is False


def test_health_and_incident_get():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    record = STORE.create("t", "sales_daily failed at 02:14 UTC because Athena timed out xx", utc_now())
    record.status = IncidentStatus.HUMAN_REVIEW
    STORE.save(record)
    got = client.get(f"/incidents/{record.id}")
    assert got.status_code == 200
    timeline = client.get(f"/incidents/{record.id}/timeline")
    assert timeline.status_code == 200


def test_audit_trail_integrity():
    from app.graph.routing import append_event
    from app.graph.state import empty_state

    state = empty_state(incident_id="abc")
    append_event(state, "incident_received", "accepted")
    append_event(state, "jev_triage", "called jev")
    ids = [e["id"] for e in state["timeline"]]
    assert len(ids) == len(set(ids))
    assert [e["node"] for e in state["timeline"]] == ["incident_received", "jev_triage"]
