from __future__ import annotations

from typing import Any

from app.integrations.qdrant import QdrantStore, QdrantUnavailable


def retrieve_evidence(store: QdrantStore, incident_text: str) -> dict[str, Any]:
    try:
        incidents = store.search(incident_text, limit=5, kind="incident")
        runbooks = store.search(incident_text, limit=5, kind="runbook")
        postmortems = store.search(incident_text, limit=3, kind="postmortem")
        procedures = store.search(incident_text, limit=3, kind="procedure")
        return {
            "available": True,
            "historical_incidents": incidents,
            "runbooks": runbooks,
            "postmortems": postmortems,
            "procedures": procedures,
        }
    except QdrantUnavailable as exc:
        return {"available": False, "error": str(exc)}
