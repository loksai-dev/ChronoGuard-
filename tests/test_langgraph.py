from app.graph.routing import route_after_risk, route_after_triage, route_after_verification
from app.graph.state import empty_state


def test_triage_router_branches():
    blocked = empty_state(triage={"recommended_route": "blocked", "is_malicious": True})
    hitl = empty_state(triage={"recommended_route": "human_review", "requires_human_review": True})
    go = empty_state(triage={"recommended_route": "investigate", "requires_human_review": False})
    assert route_after_triage(blocked) == "blocked"
    assert route_after_triage(hitl) == "human_review"
    assert route_after_triage(go) == "investigation"


def test_verification_retry_then_human():
    state = empty_state(retry_count=0, max_retries=3, verification={"verification_status": "failed"})
    assert route_after_verification(state) == "retry_investigation"
    state["retry_count"] = 3
    assert route_after_verification(state) == "human_review"


def test_risk_gate_approval():
    state = empty_state(remediation_plan=[{"requires_approval": True}], approval={})
    assert route_after_risk(state) == "human_approval"
    state["approval"] = {"approved": True}
    assert route_after_risk(state) == "remediation_executor"
