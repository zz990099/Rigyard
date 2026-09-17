"""Stable scenario plan rendering shared by direct CLI and menu."""

from __future__ import annotations

from ..scenarios.models import ComposeSupervisorPlan, ScenarioPlan


def describe_scenario(plan: ScenarioPlan) -> tuple[str, ...]:
    lines = [
        f"Scenario: {plan.scene_name}",
        f"Profile: {plan.profile_name}",
        "Backend: " + ("compose-supervisor" if isinstance(plan, ComposeSupervisorPlan) else "tmux"),
        "Groups: " + ", ".join(group.name for group in plan.groups),
    ]
    if isinstance(plan, ComposeSupervisorPlan):
        lines.extend(
            (
                f"Compose file: {plan.compose_file}",
                f"Compose project: {plan.project_name}",
                f"Supervisor configs: {plan.supervisor_config_dir}",
            )
        )
    else:
        lines.extend(
            (
                f"tmux session: {plan.session}",
                f"Attach after start: {plan.attach}",
                f"Replace existing: {plan.replace}",
            )
        )
        if plan.compose_file is not None:
            lines.extend((
                f"Compose file: {plan.compose_file}",
                f"Compose project: {plan.project_name}",
                "Container startup: stop, up -d, wait for readiness",
                f"Wait timeout: {plan.wait_timeout_seconds}s",
            ))
    return tuple(lines)
