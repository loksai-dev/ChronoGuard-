from __future__ import annotations

from typing import Any

from app.models import AllowedRemediation, RemediationAction
from app.remediation.world import WORLD

ALLOWLIST = {item.value for item in AllowedRemediation}


class RemediationRefused(RuntimeError):
    pass


def execute_actions(
    actions: list[RemediationAction],
    *,
    approved: bool,
    force_fail: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in actions:
        if action.action.value not in ALLOWLIST:
            raise RemediationRefused(f"Action {action.action} is not on the allowlist")
        if action.requires_approval and not approved:
            raise RemediationRefused(f"Action {action.action.value} requires human approval")
        outcome = WORLD.apply(action.action.value, action.target, succeed=not force_fail)
        results.append(
            {
                "action": action.action.value,
                "target": action.target,
                "command_accepted": outcome["ok"],
                "world": outcome.get("state"),
                "note": "Command acceptance is not resolution. Verification is required.",
            }
        )
    return results
