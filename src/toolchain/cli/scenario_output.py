"""Stable scenario plan rendering shared by direct CLI and menu."""

from __future__ import annotations

from ..scenarios.models import ComposeSupervisorPlan, ScenarioPlan


def describe_scenario(plan: ScenarioPlan) -> tuple[str, ...]:
    lines = [
        f"Scenario: {plan.scene_name}",
        f"Profile: {plan.profile_name}",
        "Backend: " + ("compose-supervisor" if isinstance(plan, ComposeSupervisorPlan) else "tmux"),
        "Instances: " + ", ".join(instance.name for instance in plan.instances),
    ]
    if isinstance(plan, ComposeSupervisorPlan):
        lines.extend(
            (
                f"Compose file: {plan.compose_file}",
                f"Compose project: {plan.project_name}",
                f"Supervisor configs: {plan.supervisor_config_dir}",
            )
        )
        lines.extend(
            f"Instance {instance.name}: service={instance.service or 'unset'}; "
            "programs=" + ", ".join(group.name for group in instance.groups)
            for instance in plan.instances
        )
        return tuple(lines)

    lines.extend(
        (
            f"tmux session: {plan.session}",
            f"Attach after start: {plan.attach}",
            f"Replace existing: {plan.replace}",
        )
    )
    if plan.compose_file is None:
        lines.extend(
            (
                f"Container restart: {plan.restart_container}",
                f"Mouse mode: {'on' if plan.mouse else 'off'}",
                f"Keep pane alive: {plan.keep_alive}",
            )
        )
    else:
        lines.extend(
            (
                f"Compose file: {plan.compose_file}",
                f"Compose project: {plan.project_name}",
                "Container startup: stop, up -d, wait for readiness",
                f"Wait timeout: {plan.wait_timeout_seconds}s",
                f"Mouse mode: {'on' if plan.mouse else 'off'}",
                f"Keep pane alive: {plan.keep_alive}",
            )
        )
    lines.extend(
        f"Window {instance.name}: {instance.container or 'unresolved'} -> "
        + ", ".join(group.name for group in instance.groups)
        for instance in plan.instances
    )
    return tuple(lines)
