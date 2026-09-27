from __future__ import annotations

from app.models import AllowedRemediation, RemediationAction, RemediationRisk, RootCausePackage, TriageDecision

HIGH_RISK_ACTIONS = {
    AllowedRemediation.ROLLBACK_DEPLOYMENT,
}

APPROVAL_ALWAYS = {
    RemediationRisk.HIGH,
}


def plan_remediation(
    triage: TriageDecision,
    rca: RootCausePackage | None,
) -> list[RemediationAction]:
    target = triage.target_component or "sales_daily"
    actions: list[RemediationAction] = []

    if target in {"athena", "query_service"} or triage.reason_code.value in {
        "dependency_failure",
        "deployment_regression",
        "pipeline_timeout",
    }:
        actions.append(
            RemediationAction(
                action=AllowedRemediation.RESTART_SERVICE,
                target="query_service",
                risk_level=RemediationRisk.MEDIUM,
                reason="Query service deployed at 01:50 UTC and Athena timed out; restart is the least invasive recovery.",
                expected_effect="Athena and query_service return to healthy; error rate drops.",
                rollback_action="none",
                requires_approval=True,
            )
        )
        actions.append(
            RemediationAction(
                action=AllowedRemediation.RERUN_PIPELINE,
                target="sales_daily",
                risk_level=RemediationRisk.LOW,
                reason="sales_fact_detail is stale until sales_daily completes after Athena is healthy.",
                expected_effect="sales_daily succeeds and sales_fact_detail becomes fresh.",
                rollback_action="pause_pipeline",
                requires_approval=False,
            )
        )
    else:
        actions.append(
            RemediationAction(
                action=AllowedRemediation.RERUN_PIPELINE,
                target=target if target != "unknown" else "sales_daily",
                risk_level=RemediationRisk.LOW,
                reason=rca.recommended_action if rca else "Retry the failed pipeline after investigation.",
                expected_effect="Pipeline completes successfully.",
                rollback_action="pause_pipeline",
                requires_approval=False,
            )
        )

    if triage.remediation_risk == RemediationRisk.HIGH or triage.category.value == "security":
        for action in actions:
            action.risk_level = RemediationRisk.HIGH
            action.requires_approval = True

    if triage.is_malicious:
        return []
    return actions


def risk_requires_approval(actions: list[RemediationAction], triage: TriageDecision) -> bool:
    if triage.requires_human_review:
        return True
    if triage.remediation_risk in APPROVAL_ALWAYS:
        return True
    return any(action.requires_approval or action.action in HIGH_RISK_ACTIONS for action in actions)
