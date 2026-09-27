from fastapi import APIRouter, HTTPException

from app.engine import get_engine
from app.models import IncidentCreate
from app.observability.logging import audit
from app.services import STORE

router = APIRouter()


@router.post("/incidents")
async def create_incident(payload: IncidentCreate) -> dict:
    engine = get_engine()
    record = await engine.submit(payload)
    return record.model_dump(mode="json")


@router.get("/incidents")
async def list_incidents() -> dict:
    return {"items": [item.model_dump(mode="json") for item in STORE.list()]}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str) -> dict:
    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return record.model_dump(mode="json")


@router.get("/incidents/{incident_id}/timeline")
async def get_timeline(incident_id: str) -> dict:
    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident_id": incident_id, "timeline": [e.model_dump(mode="json") for e in record.timeline]}


@router.get("/incidents/{incident_id}/graph")
async def get_graph(incident_id: str) -> dict:
    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    engine = get_engine()
    valid_at = "2026-09-27T02:00:00Z"
    known_at = "2026-09-27T02:00:00Z"
    world = engine.neo4j.dependencies_valid_at(valid_at) if engine.neo4j else []
    knowledge = engine.neo4j.knowledge_at(known_at) if engine.neo4j else []
    return {
        "incident_id": incident_id,
        "snapshot": record.graph_snapshot,
        "query_a_world_at_0200": world,
        "query_b_knowledge_at_0200": knowledge,
        "temporal_state": record.temporal_state,
    }


@router.get("/incidents/{incident_id}/evidence")
async def get_evidence(incident_id: str) -> dict:
    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {
        "incident_id": incident_id,
        "triage": record.triage.model_dump(mode="json") if record.triage else None,
        "historical": record.historical_hits,
        "rca": record.rca.model_dump(mode="json") if record.rca else None,
        "verification": record.verification_evidence,
    }


@router.post("/incidents/{incident_id}/retry")
async def retry_incident(incident_id: str) -> dict:
    engine = get_engine()
    try:
        record = await engine.resume(incident_id, approval={"approved": False, "investigate_anyway": True})
    except KeyError:
        raise HTTPException(status_code=404, detail="incident not found")
    audit("incident_retry", incident_id=incident_id)
    return record.model_dump(mode="json")
