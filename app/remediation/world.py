from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any


class WorldSimulator:
    """In-memory production-like state. Remediation never shells out."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state: dict[str, Any] = {
            "pipeline_status": {"sales_daily": "failed"},
            "service_health": {"query_service": "degraded", "athena": "timeout", "airflow": "healthy"},
            "error_rate": {"query_service": 0.42, "athena": 0.31},
            "dependency_health": {"athena->sales_fact_detail": "stale"},
            "table_freshness": {"sales_fact_detail": "stale"},
            "deployments": {"query_service": "2026.09.27.0150"},
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def reset_demo(self) -> None:
        with self._lock:
            self._state = {
                "pipeline_status": {"sales_daily": "failed"},
                "service_health": {"query_service": "degraded", "athena": "timeout", "airflow": "healthy"},
                "error_rate": {"query_service": 0.42, "athena": 0.31},
                "dependency_health": {"athena->sales_fact_detail": "stale"},
                "table_freshness": {"sales_fact_detail": "stale"},
                "deployments": {"query_service": "2026.09.27.0150"},
            }

    def apply(self, action: str, target: str, succeed: bool = True) -> dict[str, Any]:
        with self._lock:
            if not succeed:
                return {"ok": False, "state": deepcopy(self._state), "reason": "simulated_action_failed"}
            if action == "rerun_pipeline" and target == "sales_daily":
                if self._state["service_health"].get("athena") == "healthy":
                    self._state["pipeline_status"]["sales_daily"] = "succeeded"
                    self._state["table_freshness"]["sales_fact_detail"] = "fresh"
                    self._state["dependency_health"]["athena->sales_fact_detail"] = "healthy"
                else:
                    self._state["pipeline_status"]["sales_daily"] = "running"
            elif action == "restart_service":
                self._state["service_health"][target] = "healthy"
                if target == "athena":
                    self._state["error_rate"]["athena"] = 0.01
                if target == "query_service":
                    self._state["error_rate"]["query_service"] = 0.02
                    self._state["service_health"]["athena"] = "healthy"
                    self._state["error_rate"]["athena"] = 0.02
            elif action == "rollback_deployment" and target == "query_service":
                self._state["deployments"]["query_service"] = "2026.09.26.stable"
                self._state["service_health"]["query_service"] = "healthy"
                self._state["service_health"]["athena"] = "healthy"
                self._state["error_rate"]["query_service"] = 0.01
                self._state["error_rate"]["athena"] = 0.01
            elif action == "invalidate_cache":
                self._state.setdefault("cache", {})[target] = "invalidated"
            elif action == "pause_pipeline":
                self._state["pipeline_status"][target] = "paused"
            return {"ok": True, "state": deepcopy(self._state)}


WORLD = WorldSimulator()
