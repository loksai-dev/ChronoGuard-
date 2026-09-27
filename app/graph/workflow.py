from __future__ import annotations

import asyncio
import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.routing import route_after_risk, route_after_triage, route_after_verification
from app.graph.state import AgentState
from app.observability.metrics import LANGGRAPH_LATENCY


def build_graph(ctx: nodes.GraphContext) -> Any:
    graph = StateGraph(AgentState)

    async def _incident_received(state: AgentState) -> AgentState:
        return nodes.incident_received(state)

    async def _jev_triage(state: AgentState) -> AgentState:
        return await nodes.jev_triage(state, ctx)

    async def _triage_router(state: AgentState) -> AgentState:
        return nodes.triage_router(state)

    async def _blocked(state: AgentState) -> AgentState:
        return nodes.blocked(state)

    async def _human_review(state: AgentState) -> AgentState:
        return nodes.human_review(state)

    async def _investigation(state: AgentState) -> AgentState:
        return nodes.investigation(state)

    async def _investigation_parallel(state: AgentState) -> AgentState:
        dep, temporal, retrieval = await asyncio.gather(
            asyncio.to_thread(nodes.dependency_mapper, dict(state), ctx),
            asyncio.to_thread(nodes.temporal_state_reconstructor, dict(state), ctx),
            asyncio.to_thread(nodes.historical_retrieval, dict(state), ctx),
        )
        merged = dict(state)
        merged.update(
            {
                "dependencies": dep.get("dependencies"),
                "temporal_state": temporal.get("temporal_state"),
                "retrieval": retrieval.get("retrieval"),
                "timeline": _merge_timeline(state, dep, temporal, retrieval),
                "current_node": "investigation_parallel",
            }
        )
        return merged  # type: ignore[return-value]

    async def _evidence_aggregator(state: AgentState) -> AgentState:
        return nodes.evidence_aggregator(state)

    async def _rca(state: AgentState) -> AgentState:
        return await nodes.root_cause_analysis(state, ctx)

    async def _planner(state: AgentState) -> AgentState:
        return nodes.remediation_planner(state)

    async def _risk(state: AgentState) -> AgentState:
        return nodes.risk_gate(state)

    async def _human_approval(state: AgentState) -> AgentState:
        return nodes.human_approval(state)

    async def _executor(state: AgentState) -> AgentState:
        return nodes.remediation_executor(state)

    async def _verification(state: AgentState) -> AgentState:
        return nodes.verification(state)

    async def _resolved(state: AgentState) -> AgentState:
        return nodes.resolved(state)

    async def _retry(state: AgentState) -> AgentState:
        return nodes.retry_investigation(state)

    graph.add_node("incident_received", _incident_received)
    graph.add_node("jev_triage", _jev_triage)
    graph.add_node("triage_router", _triage_router)
    graph.add_node("blocked", _blocked)
    graph.add_node("human_review", _human_review)
    graph.add_node("investigation", _investigation)
    graph.add_node("investigation_parallel", _investigation_parallel)
    graph.add_node("evidence_aggregator", _evidence_aggregator)
    graph.add_node("root_cause_analysis", _rca)
    graph.add_node("remediation_planner", _planner)
    graph.add_node("risk_gate", _risk)
    graph.add_node("human_approval", _human_approval)
    graph.add_node("remediation_executor", _executor)
    graph.add_node("verification", _verification)
    graph.add_node("resolved", _resolved)
    graph.add_node("retry_investigation", _retry)

    graph.add_edge(START, "incident_received")
    graph.add_edge("incident_received", "jev_triage")
    graph.add_edge("jev_triage", "triage_router")
    graph.add_conditional_edges(
        "triage_router",
        route_after_triage,
        {
            "blocked": "blocked",
            "human_review": "human_review",
            "investigation": "investigation",
        },
    )
    graph.add_edge("blocked", END)
    graph.add_edge("human_review", END)
    graph.add_edge("investigation", "investigation_parallel")
    graph.add_edge("investigation_parallel", "evidence_aggregator")
    graph.add_edge("evidence_aggregator", "root_cause_analysis")
    graph.add_edge("root_cause_analysis", "remediation_planner")
    graph.add_edge("remediation_planner", "risk_gate")
    graph.add_conditional_edges(
        "risk_gate",
        route_after_risk,
        {
            "human_approval": "human_approval",
            "remediation_executor": "remediation_executor",
            "human_review": "human_review",
        },
    )
    graph.add_edge("human_approval", END)
    graph.add_edge("remediation_executor", "verification")
    graph.add_conditional_edges(
        "verification",
        route_after_verification,
        {
            "resolved": "resolved",
            "retry_investigation": "retry_investigation",
            "human_review": "human_review",
        },
    )
    graph.add_edge("retry_investigation", "investigation")
    graph.add_edge("resolved", END)
    return graph.compile()


async def run_graph(compiled: Any, state: AgentState) -> AgentState:
    started = time.perf_counter()
    result = await compiled.ainvoke(state)
    elapsed = (time.perf_counter() - started) * 1000
    timings = dict(result.get("timings") or {})
    timings["langgraph_execution_time_ms"] = elapsed
    result["timings"] = timings
    LANGGRAPH_LATENCY.observe(elapsed / 1000)
    return result


def _merge_timeline(base: AgentState, *others: dict[str, Any]) -> list[dict[str, Any]]:
    events = list(base.get("timeline") or [])
    seen = {item.get("id") for item in events}
    for other in others:
        for item in other.get("timeline") or []:
            if item.get("id") not in seen:
                events.append(item)
                seen.add(item.get("id"))
    return events
