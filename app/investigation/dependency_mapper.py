from __future__ import annotations

from typing import Any

from app.integrations.neo4j import Neo4jStore, Neo4jUnavailable


def map_dependencies(store: Neo4jStore, component: str | None, when: str) -> dict[str, Any]:
    try:
        graph = store.incident_graph(component, when)
        valid = store.dependencies_valid_at(when)
        return {
            "available": True,
            "component": component,
            "as_of": when,
            "ego": graph,
            "all_valid_dependencies": valid[:80],
        }
    except Neo4jUnavailable as exc:
        return {"available": False, "error": str(exc), "component": component}
