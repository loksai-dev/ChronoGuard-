# ChronoGuard

Bi-temporal incident remediation and root-cause agent.

ChronoGuard is a production-style prototype that takes a production incident, triages it with **Jev** (a TypeSafe System One decision model) through **OpenRouter**, then investigates with **LangGraph**, **Neo4j**, and **Qdrant**. Remediation is allowlisted and simulated. Incidents are never marked resolved unless verification of world state succeeds.

## Architecture

```
Incident → FastAPI → Jev (OpenRouter Decisions API) → typed TriageDecision
        → confidence / malice / HITL gate → LangGraph
        → Neo4j (valid time + transaction time) + Qdrant retrieval
        → evidence-backed RCA → allowlisted remediation → verification
        → resolved | retry | HITL
```

Jev is System-1: fast typed classification. LangGraph + optional `typesafe/jev-router` chat is System-2: investigation and prose. Routing is never a free-form LLM guess.

## Why these components

1. **Jev** — typed Choice / Noul / Score decisions with probabilities. No generated routing text to parse.
2. **OpenRouter** — authenticated gateway for Jev Decisions (`POST /api/alpha/decisions`) and chat.
3. **LangGraph** — stateful investigation/remediation graph with cycles (verification → retry).
4. **Neo4j** — topology plus bi-temporal relationship properties.
5. **Bi-temporal memory** — valid time (what was true in production) is not transaction time (what ChronoGuard had recorded).
6. **Qdrant** — semantic lookup of incidents, runbooks, procedures, postmortems.
7. **FastAPI + UI** — inspect every decision, latency, evidence, and approval gate.

## Jev configuration (do not invent APIs)

| Variable | Purpose | Default |
|---|---|---|
| `JEV_MODEL` | Jev **decision** model for typed triage | `typesafe/jev-1.13` |
| `OPENROUTER_DECISIONS_URL` | Official Decisions endpoint | `https://openrouter.ai/api/alpha/decisions` |
| `OPENROUTER_CHAT_MODEL` | Generative model for RCA prose | `typesafe/jev-router` |
| `OPENROUTER_BASE_URL` | OpenAI-compatible chat base | `https://openrouter.ai/api/v1` |

`typesafe/jev-router` is OpenRouter’s cache-aware **model router**. It is not a replacement for the Decisions API. ChronoGuard uses Jev 1.13 for triage and jev-router only for optional RCA wording.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env`. Never commit `.env`.

## Docker startup

```bash
docker compose up --build
```

- API + UI via API: http://localhost:8000
- Frontend proxy: http://localhost:3000
- Neo4j browser: http://localhost:7474
- Qdrant: http://localhost:6333

## Running the demo

1. Start the stack.
2. Open the UI.
3. Submit the seeded incident text (pre-filled).
4. Inspect Jev triage, graph, Query A vs Query B, RCA, plan.
5. Approve if the risk gate pauses.
6. Confirm verification before treating the incident as resolved.

CLI:

```bash
python scripts/demo_incident.py
```

## Tests

```bash
python -m pytest -q
```

Unit tests mock OpenRouter. The production `JevClient` always calls OpenRouter; it does not fall back to a hard-coded decision.

## Benchmark

```bash
python scripts/benchmark.py
```

Compares Jev typed routing vs chat-model JSON routing on a tiny fixture. Unmeasured fields print `NOT MEASURED`.

## API

- `POST /incidents`
- `GET /incidents/{id}`
- `GET /incidents/{id}/timeline`
- `GET /incidents/{id}/graph`
- `GET /incidents/{id}/evidence`
- `POST /incidents/{id}/approve`
- `POST /incidents/{id}/reject`
- `POST /incidents/{id}/retry`
- `GET /health`
- `GET /metrics`

## Example incident

> sales_daily failed at 02:14 UTC because Athena timed out and sales_fact_detail was not refreshed.

## Example Jev decision (shape)

Jev returns primitives, which ChronoGuard validates into:

```json
{
  "category": "pipeline",
  "severity": 7,
  "is_malicious": false,
  "target_component": "sales_daily",
  "confidence": 0.86,
  "requires_human_review": false,
  "recommended_route": "investigate",
  "reason_code": "pipeline_timeout"
}
```

Exact probabilities vary per live Jev call.

## Temporal query examples

**Query A (valid time):** dependencies true in production at `2026-09-27T02:00:00Z`  
includes `sales_daily -[:READS_FROM]-> query_service` after the 02:00 cutover.

**Query B (transaction time):** facts ChronoGuard had recorded by `2026-09-27T02:00:00Z`  
does **not** include that cutover, because ChronoGuard only recorded it at `02:35Z`.

## Security model

- API keys only from environment variables
- Pydantic input validation
- Structured audit logs
- Remediation allowlist (`restart_service`, `rollback_deployment`, `rerun_pipeline`, `invalidate_cache`, `pause_pipeline`)
- Simulated executor only — no shell, no LLM-chosen commands
- Malicious incidents are blocked
- Timeouts, retries, and HITL for high-risk actions
- Incident text is treated as untrusted (prompt-injection awareness in Jev state)

## Known limitations

- Remediation mutates an in-memory simulator, not real Airflow/Athena.
- Embeddings default to a local hashing embedder (swap via `EMBEDDING_PROVIDER=openai_compatible`).
- Incident records are in-process memory (restart clears them; graph/Qdrant persist).
- RCA chat is optional; if chat fails, rule-based hypothesis from evidence is used and labeled as hypothesis.
- Jev cannot emit free-form `target_component` strings; the choice set is the known topology plus `unknown`/`none`.

## Next improvements

- Durable incident store and LangGraph checkpointing
- Real metric/log adapters
- Calibrate Jev thresholds on labeled incidents
- Multi-cluster Neo4j and RBAC on the API
