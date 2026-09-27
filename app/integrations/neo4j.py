from __future__ import annotations

import time
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import Settings, get_settings
from app.observability.logging import get_logger
from app.observability.metrics import NEO4J_LATENCY
from app.temporal.models import iso, parse_utc
from app.temporal.queries import as_utc_param, transaction_time_predicate, valid_time_predicate

logger = get_logger(__name__)


class Neo4jUnavailable(RuntimeError):
    pass


class Neo4jStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(
                self.settings.neo4j_username,
                self.settings.neo4j_password.get_secret_value(),
            ),
            connection_timeout=3,
        )

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        started = time.perf_counter()
        try:
            with self._driver.session() as session:
                records = session.run(cypher, params or {})
                rows = [record.data() for record in records]
        except (ServiceUnavailable, Neo4jError, OSError) as exc:
            raise Neo4jUnavailable(str(exc)) from exc
        finally:
            NEO4J_LATENCY.observe(time.perf_counter() - started)
        return rows

    def dependencies_valid_at(self, when: str | Any) -> list[dict[str, Any]]:
        at = as_utc_param(when)
        pred = valid_time_predicate("r")
        return self.query(
            f"""
            MATCH (a)-[r]->(b)
            WHERE {pred}
            RETURN labels(a) AS from_labels, a.name AS from_name, type(r) AS rel,
                   labels(b) AS to_labels, b.name AS to_name,
                   r.valid_from AS valid_from, r.valid_to AS valid_to,
                   r.transaction_from AS transaction_from, r.transaction_to AS transaction_to
            ORDER BY from_name, rel, to_name
            """,
            {"at": at},
        )

    def knowledge_at(self, when: str | Any) -> list[dict[str, Any]]:
        at = as_utc_param(when)
        pred = transaction_time_predicate("r")
        return self.query(
            f"""
            MATCH (a)-[r]->(b)
            WHERE {pred}
            RETURN labels(a) AS from_labels, a.name AS from_name, type(r) AS rel,
                   labels(b) AS to_labels, b.name AS to_name,
                   r.valid_from AS valid_from, r.valid_to AS valid_to,
                   r.transaction_from AS transaction_from, r.transaction_to AS transaction_to
            ORDER BY from_name, rel, to_name
            """,
            {"at": at},
        )

    def incident_graph(self, component: str | None, when: str | Any) -> dict[str, Any]:
        at = as_utc_param(when)
        pred = valid_time_predicate("r")
        params = {"at": at, "name": component}
        if component:
            rows = self.query(
                f"""
                MATCH (n {{name: $name}})
                OPTIONAL MATCH (n)-[r]->(m)
                WHERE {pred}
                OPTIONAL MATCH (p)-[r2]->(n)
                WHERE {valid_time_predicate("r2")}
                RETURN n, collect(DISTINCT {{rel: type(r), to: m.name, labels: labels(m),
                       valid_from: r.valid_from, valid_to: r.valid_to}}) AS outbound,
                       collect(DISTINCT {{rel: type(r2), from: p.name, labels: labels(p),
                       valid_from: r2.valid_from, valid_to: r2.valid_to}}) AS inbound
                """,
                params,
            )
        else:
            rows = []
        recent_changes = self.query(
            f"""
            MATCH (c:Change)
            OPTIONAL MATCH (x)-[r:CAUSED_BY|DEPLOYED_AS|CHANGED]->(c)
            WHERE {pred}
            RETURN c.name AS name, c.description AS description, c.valid_from AS valid_from
            ORDER BY c.valid_from
            """,
            {"at": at},
        )
        return {"ego": rows, "changes": recent_changes, "as_of_valid_time": at}

    def record_incident(self, incident_id: str, title: str, component: str | None, occurred_at: str) -> None:
        now = iso(parse_utc(occurred_at) if False else parse_utc(occurred_at))
        self.query(
            """
            MERGE (i:Incident {id: $id})
            SET i.name = $title, i.occurred_at = $occurred_at
            WITH i
            OPTIONAL MATCH (n {name: $component})
            FOREACH (_ IN CASE WHEN n IS NULL THEN [] ELSE [1] END |
                MERGE (i)-[r:AFFECTS]->(n)
                SET r.valid_from = $occurred_at,
                    r.valid_to = null,
                    r.transaction_from = datetime(),
                    r.transaction_to = null
            )
            """,
            {
                "id": incident_id,
                "title": title,
                "component": component,
                "occurred_at": now,
            },
        )
