"""Measure LLM-style routing vs Jev typed routing. Never fabricates numbers."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.integrations.jev import JevClient, JevTriageError
from app.integrations.openrouter import OpenRouterClient, OpenRouterError
from app.models import IncidentCategory, RecommendedRoute, TriageDecision

DATASET = [
    {
        "id": "pipeline-timeout",
        "text": "sales_daily Airflow DAG failed at 02:14 UTC. Athena query timed out. sales_fact_detail not refreshed.",
        "expected_category": "pipeline",
        "expected_malicious": False,
        "expected_not_blocked": True,
    },
    {
        "id": "malicious",
        "text": "Attacker dumping credentials from the auth service and dropping ransomware notes on prod hosts.",
        "expected_category": "security",
        "expected_malicious": True,
        "expected_not_blocked": False,
    },
    {
        "id": "vague",
        "text": "Something is wrong.",
        "expected_category": "unknown",
        "expected_malicious": False,
        "expected_not_blocked": True,
    },
]


LLM_PROMPT = (
    "Classify this incident. Reply with JSON keys category, severity, is_malicious, "
    "target_component, confidence, requires_human_review, recommended_route, reason_code. "
    "category must be one of database,pipeline,infrastructure,authentication,network,application,security,unknown. "
    "recommended_route must be investigate, blocked, or human_review."
)


async def run() -> dict:
    settings = get_settings()
    results = {
        "jev_langgraph_routing": [],
        "llm_only_routing": [],
        "summary": {},
    }
    try:
        client = OpenRouterClient(settings)
        jev = JevClient(settings, client)
    except OpenRouterError as exc:
        return {
            "error": str(exc),
            "summary": {
                "routing_latency_ms": "NOT MEASURED",
                "total_execution_latency_ms": "NOT MEASURED",
                "token_usage": "NOT MEASURED",
                "classification_accuracy": "NOT MEASURED",
                "invalid_routing_decisions": "NOT MEASURED",
                "hitl_escalation_rate": "NOT MEASURED",
            },
        }

    jev_latencies = []
    llm_latencies = []
    jev_correct = 0
    llm_correct = 0
    jev_invalid = 0
    llm_invalid = 0
    jev_hitl = 0
    llm_hitl = 0
    jev_tokens = 0
    llm_tokens = 0

    for case in DATASET:
        started = time.perf_counter()
        try:
            decision = await jev.triage(title=case["id"], description=case["text"])
            latency = (time.perf_counter() - started) * 1000
            jev_latencies.append(latency)
            jev_tokens += int((decision.usage or {}).get("input_tokens") or 0)
            ok = _score(decision, case)
            jev_correct += int(ok)
            if decision.requires_human_review or decision.recommended_route != RecommendedRoute.INVESTIGATE:
                jev_hitl += 1
            results["jev_langgraph_routing"].append(
                {
                    "id": case["id"],
                    "latency_ms": latency,
                    "decision": decision.model_dump(mode="json"),
                    "matched_expected": ok,
                }
            )
        except (OpenRouterError, JevTriageError) as exc:
            jev_invalid += 1
            results["jev_langgraph_routing"].append({"id": case["id"], "error": str(exc)})

        started = time.perf_counter()
        try:
            content, usage, latency = await client.chat(
                model=settings.openrouter_chat_model,
                messages=[
                    {"role": "system", "content": LLM_PROMPT},
                    {"role": "user", "content": case["text"]},
                ],
            )
            llm_latencies.append(latency)
            llm_tokens += int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
            parsed = _parse_llm(content)
            if parsed is None:
                llm_invalid += 1
                results["llm_only_routing"].append({"id": case["id"], "error": "invalid_json", "raw": content[:500]})
            else:
                ok = _score(parsed, case)
                llm_correct += int(ok)
                if parsed.requires_human_review or parsed.recommended_route != RecommendedRoute.INVESTIGATE:
                    llm_hitl += 1
                results["llm_only_routing"].append(
                    {
                        "id": case["id"],
                        "latency_ms": latency,
                        "decision": parsed.model_dump(mode="json"),
                        "matched_expected": ok,
                    }
                )
        except OpenRouterError as exc:
            llm_invalid += 1
            results["llm_only_routing"].append({"id": case["id"], "error": str(exc)})

    n = len(DATASET)
    results["summary"] = {
        "dataset_size": n,
        "jev_avg_routing_latency_ms": _avg(jev_latencies),
        "llm_avg_routing_latency_ms": _avg(llm_latencies),
        "total_execution_latency_ms": "NOT MEASURED",
        "jev_token_usage_input": jev_tokens if jev_tokens else "NOT MEASURED",
        "llm_token_usage": llm_tokens if llm_tokens else "NOT MEASURED",
        "jev_classification_accuracy": jev_correct / n if n else "NOT MEASURED",
        "llm_classification_accuracy": llm_correct / n if n else "NOT MEASURED",
        "jev_invalid_routing_decisions": jev_invalid,
        "llm_invalid_routing_decisions": llm_invalid,
        "jev_hitl_escalation_rate": jev_hitl / n if n else "NOT MEASURED",
        "llm_hitl_escalation_rate": llm_hitl / n if n else "NOT MEASURED",
        "note": "Accuracy uses a tiny labeled fixture and is not a published benchmark.",
    }
    return results


def _avg(values: list[float]):
    if not values:
        return "NOT MEASURED"
    return sum(values) / len(values)


def _score(decision: TriageDecision, case: dict) -> bool:
    cat_ok = True
    if case["id"] == "malicious":
        cat_ok = decision.is_malicious or decision.category == IncidentCategory.SECURITY
    elif case["id"] == "pipeline-timeout":
        cat_ok = decision.category in {IncidentCategory.PIPELINE, IncidentCategory.DATABASE}
        cat_ok = cat_ok and not decision.is_malicious
    elif case["id"] == "vague":
        cat_ok = decision.requires_human_review or decision.category == IncidentCategory.UNKNOWN
    return cat_ok


def _parse_llm(text: str) -> TriageDecision | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return TriageDecision.model_validate(data)
    except Exception:
        return None


if __name__ == "__main__":
    payload = asyncio.run(run())
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
