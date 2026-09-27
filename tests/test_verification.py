from app.remediation.executor import execute_actions
from app.remediation.verifier import verify_world
from app.remediation.world import WORLD
from app.models import AllowedRemediation, RemediationAction, RemediationRisk, VerificationStatus


def test_verification_fails_if_only_command_succeeded():
    WORLD.reset_demo()
    execute_actions(
        [
            RemediationAction(
                action=AllowedRemediation.RERUN_PIPELINE,
                target="sales_daily",
                risk_level=RemediationRisk.LOW,
                reason="x",
                expected_effect="y",
                rollback_action="pause_pipeline",
                requires_approval=False,
            )
        ],
        approved=True,
    )
    result = verify_world()
    assert result["verification_status"] != VerificationStatus.RESOLVED.value


def test_verification_resolved_after_full_recovery():
    WORLD.reset_demo()
    execute_actions(
        [
            RemediationAction(
                action=AllowedRemediation.RESTART_SERVICE,
                target="query_service",
                risk_level=RemediationRisk.MEDIUM,
                reason="x",
                expected_effect="y",
                rollback_action="none",
                requires_approval=True,
            ),
            RemediationAction(
                action=AllowedRemediation.RERUN_PIPELINE,
                target="sales_daily",
                risk_level=RemediationRisk.LOW,
                reason="x",
                expected_effect="y",
                rollback_action="pause_pipeline",
                requires_approval=False,
            ),
        ],
        approved=True,
    )
    result = verify_world()
    assert result["verification_status"] == VerificationStatus.RESOLVED.value
