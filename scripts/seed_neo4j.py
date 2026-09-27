from __future__ import annotations

from datetime import datetime, timezone

from neo4j import GraphDatabase

DEMO_DAY = "2026-09-27"


def _dt(hour: int, minute: int, second: int = 0) -> str:
    return datetime(2026, 9, 27, hour, minute, second, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


SEED_CYPHER = """
MATCH (n) DETACH DELETE n;

CREATE (airflow:Service:Pipeline {name:'airflow', kind:'orchestrator'})
CREATE (sales:Pipeline {name:'sales_daily', kind:'airflow_dag'})
CREATE (query:Service {name:'query_service', kind:'app'})
CREATE (athena:Database {name:'athena', kind:'query_engine'})
CREATE (table:Table {name:'sales_fact_detail', kind:'warehouse_table'})
CREATE (deployOld:Deployment {name:'query_service:2026.09.26.stable'})
CREATE (deployNew:Deployment {name:'query_service:2026.09.27.0150'})
CREATE (change:Change {name:'query_service_cutover', description:'sales_daily now queries Athena through query_service'})
CREATE (team:Team {name:'data-platform'})
CREATE (runbook:Runbook {name:'athena_timeout_runbook'})
CREATE (hist:Incident {name:'hist_sales_daily_athena_timeout_2026_08', id:'hist-001'})

CREATE (sales)-[:RUNS_ON {valid_from:$t0130, valid_to:null, transaction_from:$t0132, transaction_to:null}]->(airflow)
CREATE (sales)-[:READS_FROM {valid_from:$t0130, valid_to:$t0200, transaction_from:$t0132, transaction_to:null}]->(athena)
CREATE (sales)-[:WRITES_TO {valid_from:$t0130, valid_to:null, transaction_from:$t0132, transaction_to:null}]->(table)
CREATE (query)-[:DEPENDS_ON {valid_from:$t0130, valid_to:null, transaction_from:$t0132, transaction_to:null}]->(athena)
CREATE (query)-[:DEPLOYED_AS {valid_from:$t0000, valid_to:$t0150, transaction_from:$t0001, transaction_to:null}]->(deployOld)
CREATE (query)-[:DEPLOYED_AS {valid_from:$t0150, valid_to:null, transaction_from:$t0152, transaction_to:null}]->(deployNew)
CREATE (sales)-[:READS_FROM {valid_from:$t0200, valid_to:null, transaction_from:$t0235, transaction_to:null}]->(query)
CREATE (sales)-[:CHANGED {valid_from:$t0200, valid_to:null, transaction_from:$t0235, transaction_to:null}]->(change)
CREATE (athena)-[:HEALTH {status:'healthy', valid_from:$t0130, valid_to:$t0214, transaction_from:$t0132, transaction_to:null}]->(athena)
CREATE (hist)-[:AFFECTS {valid_from:$hist_from, valid_to:$hist_to, transaction_from:$hist_from, transaction_to:null}]->(sales)
CREATE (hist)-[:HAS_RUNBOOK {valid_from:$hist_from, valid_to:null, transaction_from:$hist_from, transaction_to:null}]->(runbook)
CREATE (team)-[:OWNS {valid_from:$t0000, valid_to:null, transaction_from:$t0001, transaction_to:null}]->(sales)
CREATE (team)-[:OWNS {valid_from:$t0000, valid_to:null, transaction_from:$t0001, transaction_to:null}]->(query);
"""


def seed(uri: str, user: str, password: str) -> None:
    params = {
        "t0000": _dt(0, 0),
        "t0001": _dt(0, 1),
        "t0130": _dt(1, 30),
        "t0132": _dt(1, 32),
        "t0150": _dt(1, 50),
        "t0152": _dt(1, 52),
        "t0200": _dt(2, 0),
        "t0214": _dt(2, 14),
        "t0235": _dt(2, 35),
        "hist_from": "2026-08-12T02:11:00Z",
        "hist_to": "2026-08-12T03:00:00Z",
    }
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        session.run(SEED_CYPHER, params)
    driver.close()


if __name__ == "__main__":
    import os

    seed(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        os.getenv("NEO4J_USERNAME", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "chronoguard"),
    )
    print("Neo4j seed complete")
