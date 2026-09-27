from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

INCIDENTS_TOTAL = Counter(
    "chronoguard_incidents_total",
    "Incidents received",
    ["status"],
)
JEV_LATENCY = Histogram(
    "chronoguard_jev_latency_seconds",
    "Jev decision latency",
)
OPENROUTER_LATENCY = Histogram(
    "chronoguard_openrouter_latency_seconds",
    "OpenRouter round-trip latency",
)
NEO4J_LATENCY = Histogram(
    "chronoguard_neo4j_query_latency_seconds",
    "Neo4j query latency",
)
QDRANT_LATENCY = Histogram(
    "chronoguard_qdrant_latency_seconds",
    "Qdrant query latency",
)
LANGGRAPH_LATENCY = Histogram(
    "chronoguard_langgraph_execution_seconds",
    "LangGraph execution time",
)
RESOLUTION_LATENCY = Histogram(
    "chronoguard_resolution_seconds",
    "End-to-end resolution time",
)
RETRY_COUNT = Gauge(
    "chronoguard_retry_count",
    "Current retry count for an incident",
    ["incident_id"],
)
TRIAGE_CONFIDENCE = Histogram(
    "chronoguard_triage_confidence",
    "Jev triage confidence",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
