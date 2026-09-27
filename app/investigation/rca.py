from __future__ import annotations

import json
from typing import Any

from app.integrations.openrouter import OpenRouterClient, OpenRouterError
from app.models import EvidenceItem, EvidenceKind, RootCausePackage, TriageDecision


RCA_SYSTEM = (
    "You are ChronoGuard's RCA writer. You must only reason from the provided evidence package. "
    "Never invent logs, graph edges, or historical incidents. "
    "Clearly separate OBSERVED FACT, INFERRED FACT, and HYPOTHESIS. "
    "Never present a hypothesis as a confirmed root cause. "
    "Return compact JSON with keys: hypothesis, confidence (0-1), recommended_action, "
    "supporting (list of short strings), contradicting (list of short strings), affected (list of strings)."
)


async def build_rca(
    *,
    triage: TriageDecision,
    incident_text: str,
    dependencies: dict[str, Any],
    temporal: dict[str, Any],
    retrieval: dict[str, Any],
    observed: dict[str, Any],
    chat: OpenRouterClient | None,
    chat_model: str,
) -> RootCausePackage:
    observed_items = _observed_evidence(triage, dependencies, temporal, retrieval, observed)
    inferred_items = _inferred_evidence(dependencies, temporal, retrieval)
    package = {
        "incident": incident_text,
        "triage": triage.model_dump(mode="json"),
        "observed": [i.model_dump(mode="json") for i in observed_items],
        "inferred": [i.model_dump(mode="json") for i in inferred_items],
        "dependencies_available": dependencies.get("available"),
        "temporal_available": temporal.get("available"),
        "retrieval_available": retrieval.get("available"),
        "temporal_diff": (temporal or {}).get("differs"),
        "historical": retrieval.get("historical_incidents", []),
        "runbooks": retrieval.get("runbooks", []),
        "observed_world": observed,
    }

    hypothesis = _deterministic_hypothesis(triage, temporal, retrieval, observed)
    confidence = min(triage.confidence, 0.82)
    recommended = "rerun_pipeline on sales_daily after confirming Athena health"
    if chat is not None:
        try:
            content, _, _ = await chat.chat(
                model=chat_model,
                messages=[
                    {"role": "system", "content": RCA_SYSTEM},
                    {"role": "user", "content": json.dumps(package, default=str)[:12000]},
                ],
            )
            parsed = _extract_json(content)
            if parsed:
                hypothesis = parsed.get("hypothesis") or hypothesis
                recommended = parsed.get("recommended_action") or recommended
                try:
                    confidence = float(parsed.get("confidence", confidence))
                except (TypeError, ValueError):
                    pass
                if parsed.get("supporting"):
                    inferred_items.extend(
                        EvidenceItem(
                            id=f"llm-s-{i}",
                            kind=EvidenceKind.HYPOTHESIS,
                            source="openrouter_chat",
                            summary=str(item),
                        )
                        for i, item in enumerate(parsed["supporting"][:5])
                    )
        except OpenRouterError:
            inferred_items.append(
                EvidenceItem(
                    id="rca-chat-degraded",
                    kind=EvidenceKind.INFERRED_FACT,
                    source="openrouter_chat",
                    summary="Chat model unavailable; RCA hypothesis generated from evidence rules only.",
                )
            )

    contradicting = []
    if not dependencies.get("available"):
        contradicting.append(
            EvidenceItem(
                id="neo4j-missing",
                kind=EvidenceKind.OBSERVED_FACT,
                source="neo4j",
                summary="Dependency graph unavailable; causal links are incomplete.",
            )
        )

    return RootCausePackage(
        root_cause_hypothesis=hypothesis,
        confidence=max(0.0, min(1.0, confidence)),
        supporting_evidence=observed_items + inferred_items,
        contradicting_evidence=contradicting,
        affected_components=_affected(triage, dependencies),
        recommended_action=recommended,
    )


def _deterministic_hypothesis(
    triage: TriageDecision,
    temporal: dict[str, Any],
    retrieval: dict[str, Any],
    observed: dict[str, Any],
) -> str:
    diff = (temporal or {}).get("differs") or {}
    world_only = diff.get("world_only") or []
    change_clause = ""
    if world_only:
        change_clause = (
            f" Bi-temporal reconstruction shows production edges not yet known to ChronoGuard: {world_only[:4]}."
        )
    hist = retrieval.get("historical_incidents") or []
    hist_clause = ""
    if hist:
        title = (hist[0].get("payload") or {}).get("title")
        hist_clause = f" Similar historical incident: {title}."
    athena = observed.get("athena_status")
    return (
        f"Hypothesis (not confirmed): {triage.target_component or 'the pipeline'} failed due to "
        f"{triage.reason_code.value}. Athena observed status={athena}."
        f"{change_clause}{hist_clause}"
    )


def _observed_evidence(
    triage: TriageDecision,
    dependencies: dict[str, Any],
    temporal: dict[str, Any],
    retrieval: dict[str, Any],
    observed: dict[str, Any],
) -> list[EvidenceItem]:
    items = [
        EvidenceItem(
            id="jev-category",
            kind=EvidenceKind.OBSERVED_FACT,
            source="jev",
            summary=f"Jev category={triage.category.value} severity={triage.severity} confidence={triage.confidence:.2f}",
            payload={"triage": triage.model_dump(mode="json")},
        )
    ]
    for key, value in observed.items():
        items.append(
            EvidenceItem(
                id=f"obs-{key}",
                kind=EvidenceKind.OBSERVED_FACT,
                source="simulator",
                summary=f"{key}={value}",
            )
        )
    if retrieval.get("available"):
        for hit in (retrieval.get("historical_incidents") or [])[:3]:
            payload = hit.get("payload") or {}
            items.append(
                EvidenceItem(
                    id=f"hist-{hit.get('id')}",
                    kind=EvidenceKind.OBSERVED_FACT,
                    source="qdrant",
                    summary=payload.get("title") or payload.get("text", "")[:180],
                    score=hit.get("score"),
                    payload=hit,
                )
            )
        for hit in (retrieval.get("runbooks") or [])[:3]:
            payload = hit.get("payload") or {}
            items.append(
                EvidenceItem(
                    id=f"rb-{hit.get('id')}",
                    kind=EvidenceKind.OBSERVED_FACT,
                    source="qdrant",
                    summary=payload.get("title") or payload.get("text", "")[:180],
                    score=hit.get("score"),
                    payload=hit,
                )
            )
    return items


def _inferred_evidence(
    dependencies: dict[str, Any],
    temporal: dict[str, Any],
    retrieval: dict[str, Any],
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    if temporal.get("available"):
        items.append(
            EvidenceItem(
                id="bitemporal-diff",
                kind=EvidenceKind.INFERRED_FACT,
                source="neo4j",
                summary="Valid-time and transaction-time views of the topology differ.",
                payload=temporal.get("differs") or {},
            )
        )
    if dependencies.get("available"):
        items.append(
            EvidenceItem(
                id="dep-map",
                kind=EvidenceKind.INFERRED_FACT,
                source="neo4j",
                summary="Mapped ego-network around the affected component at incident valid time.",
                payload={"ego": dependencies.get("ego")},
            )
        )
    return items


def _affected(triage: TriageDecision, dependencies: dict[str, Any]) -> list[str]:
    names = []
    if triage.target_component:
        names.append(triage.target_component)
    for row in (dependencies.get("all_valid_dependencies") or [])[:20]:
        for key in ("from_name", "to_name"):
            value = row.get(key)
            if value and value not in names:
                names.append(value)
    return names[:12]


def _extract_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
