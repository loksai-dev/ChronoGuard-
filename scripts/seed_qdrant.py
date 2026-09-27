from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.integrations.qdrant import QdrantStore

DOCS = [
    {
        "id": "inc-hist-001",
        "kind": "incident",
        "title": "sales_daily Athena timeout August 2026",
        "text": "sales_daily Airflow DAG failed after Athena query timeout. sales_fact_detail was stale. Root hypothesis: query_service regression after deploy.",
    },
    {
        "id": "rb-athena-timeout",
        "kind": "runbook",
        "title": "Athena timeout runbook",
        "text": "If Airflow DAG fails on Athena timeout: check query_service deploy, restart query_service, confirm Athena healthy, rerun pipeline, verify sales_fact_detail freshness.",
    },
    {
        "id": "proc-rerun",
        "kind": "procedure",
        "title": "Rerun sales_daily",
        "text": "Safe remediation: rerun_pipeline target sales_daily after dependency health is green. Do not mutate warehouse tables directly.",
    },
    {
        "id": "pm-001",
        "kind": "postmortem",
        "title": "Postmortem query_service cutover",
        "text": "A previous cutover of sales_daily to query_service increased Athena timeout rate until the service was restarted and the DAG rerun.",
    },
]


def seed() -> None:
    settings = get_settings()
    store = QdrantStore(settings)
    store.upsert(DOCS)
    print("Qdrant seed complete")


if __name__ == "__main__":
    seed()
