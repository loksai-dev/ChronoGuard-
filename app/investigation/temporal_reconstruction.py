from __future__ import annotations

from typing import Any

from app.integrations.neo4j import Neo4jStore, Neo4jUnavailable


def reconstruct_temporal_state(
    store: Neo4jStore,
    *,
    valid_at: str,
    known_at: str,
) -> dict[str, Any]:
    try:
        world = store.dependencies_valid_at(valid_at)
        knowledge = store.knowledge_at(known_at)
        return {
            "available": True,
            "query_a_world_valid_at": valid_at,
            "query_b_chronoguard_knew_at": known_at,
            "world_state": world,
            "knowledge_state": knowledge,
            "differs": _summarize_diff(world, knowledge),
            "explanation": (
                "Query A uses VALID TIME: facts true in production at that instant. "
                "Query B uses TRANSACTION TIME: facts ChronoGuard had already recorded."
            ),
        }
    except Neo4jUnavailable as exc:
        return {"available": False, "error": str(exc)}


def _summarize_diff(world: list[dict[str, Any]], knowledge: list[dict[str, Any]]) -> dict[str, Any]:
    def key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (str(row.get("from_name")), str(row.get("rel")), str(row.get("to_name")))

    world_keys = {key(r) for r in world}
    known_keys = {key(r) for r in knowledge}
    return {
        "world_only": [list(k) for k in sorted(world_keys - known_keys)],
        "knowledge_only": [list(k) for k in sorted(known_keys - world_keys)],
        "shared": len(world_keys & known_keys),
    }
