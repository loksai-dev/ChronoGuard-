from fastapi import APIRouter, HTTPException

from app.engine import get_engine
from app.models import ApprovalRequest, RejectionRequest
from app.observability.logging import audit
from app.services import STORE

router = APIRouter()


@router.post("/incidents/{incident_id}/approve")
async def approve_incident(incident_id: str, payload: ApprovalRequest) -> dict:
    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    audit("approval_granted", incident_id=incident_id, approved_by=payload.approved_by)
    engine = get_engine()
    updated = await engine.resume(
        incident_id,
        approval={
            "approved": True,
            "investigate_anyway": True,
            "approved_by": payload.approved_by,
            "comment": payload.comment,
        },
    )
    return updated.model_dump(mode="json")


@router.post("/incidents/{incident_id}/reject")
async def reject_incident(incident_id: str, payload: RejectionRequest) -> dict:
    from app.models import IncidentStatus

    record = STORE.get(incident_id)
    if record is None:
        raise HTTPException(status_code=404, detail="incident not found")
    record.status = IncidentStatus.REJECTED
    record.approval = {
        "approved": False,
        "rejected_by": payload.rejected_by,
        "comment": payload.comment,
    }
    STORE.save(record)
    audit("approval_rejected", incident_id=incident_id, rejected_by=payload.rejected_by)
    return record.model_dump(mode="json")
