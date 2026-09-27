from __future__ import annotations

from typing import Any

from app.models import VerificationStatus
from app.remediation.world import WORLD


def verify_world(expected_pipeline: str = "sales_daily") -> dict[str, Any]:
    state = WORLD.snapshot()
    pipeline_ok = state["pipeline_status"].get(expected_pipeline) == "succeeded"
    athena_ok = state["service_health"].get("athena") == "healthy"
    table_ok = state["table_freshness"].get("sales_fact_detail") == "fresh"
    error_ok = all(rate < 0.05 for rate in state["error_rate"].values())
    dep_ok = all(value == "healthy" for value in state["dependency_health"].values())

    checks = {
        "pipeline_status": pipeline_ok,
        "service_health": athena_ok,
        "table_freshness": table_ok,
        "error_rate": error_ok,
        "dependency_health": dep_ok,
    }
    if all(checks.values()):
        status = VerificationStatus.RESOLVED
    elif any(checks.values()):
        status = VerificationStatus.FAILED
    else:
        status = VerificationStatus.FAILED

    if not any(checks.values()) and state["pipeline_status"].get(expected_pipeline) == "running":
        status = VerificationStatus.INCONCLUSIVE

    return {
        "verification_status": status.value,
        "checks": checks,
        "state": state,
        "note": "Resolution requires verified world state, not command success.",
    }
