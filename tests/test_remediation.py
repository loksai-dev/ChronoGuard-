import pytest

from app.models import AllowedRemediation, RemediationAction, RemediationRisk
from app.remediation.executor import RemediationRefused, execute_actions
from app.remediation.planner import plan_remediation
from app.remediation.world import WORLD
from app.integrations.jev import map_jev_answers
from tests.conftest import SAMPLE_ANSWERS
from tests.test_jev import settings


def test_remediation_approval_required():
    WORLD.reset_demo()
    decision = map_jev_answers(
        answers=SAMPLE_ANSWERS,
        settings=settings(),
        raw_body={},
        jev_latency_ms=1,
        openrouter_latency_ms=1,
    )
    plan = plan_remediation(decision, None)
    assert any(item.requires_approval for item in plan)
    with pytest.raises(RemediationRefused):
        execute_actions(plan, approved=False)


def test_remediation_succeeds_after_approval():
    WORLD.reset_demo()
    action = RemediationAction(
        action=AllowedRemediation.RESTART_SERVICE,
        target="query_service",
        risk_level=RemediationRisk.MEDIUM,
        reason="test",
        expected_effect="healthy",
        rollback_action="none",
        requires_approval=True,
    )
    results = execute_actions([action], approved=True)
    assert results[0]["command_accepted"] is True
    assert WORLD.snapshot()["service_health"]["query_service"] == "healthy"


def test_remediation_failure():
    WORLD.reset_demo()
    action = RemediationAction(
        action=AllowedRemediation.RERUN_PIPELINE,
        target="sales_daily",
        risk_level=RemediationRisk.LOW,
        reason="test",
        expected_effect="ok",
        rollback_action="pause_pipeline",
        requires_approval=False,
    )
    results = execute_actions([action], approved=True, force_fail=True)
    assert results[0]["command_accepted"] is False
