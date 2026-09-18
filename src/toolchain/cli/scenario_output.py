"""Stable scenario plan rendering shared by direct CLI and menu."""

from __future__ import annotations

from ..scenarios.models import ScenarioPlan


def describe_scenario_target(plan: ScenarioPlan) -> tuple[str, ...]:
    """Short rendering for scene management actions such as stop and down."""

    return (
        f"Scenario: {plan.scene_name}",
        f"Profile: {plan.profile_name}",
        f"tmux session: {plan.session}",
        "Instances: " + ", ".join(instance.name for instance in plan.instances),
    )


def describe_scenario(plan: ScenarioPlan) -> tuple[str, ...]:
    lines = [
        f"Scenario: {plan.scene_name}",
        f"Profile: {plan.profile_name}",
        "Runtime: tmux in "
        + ("Compose-managed containers" if plan.compose is not None else "existing containers"),
        "Instances: " + ", ".join(instance.name for instance in plan.instances),
        f"tmux session: {plan.session}",
        f"Attach after start: {plan.attach}",
        f"Replace existing: {plan.replace}",
        f"Mouse mode: {'on' if plan.mouse else 'off'}",
        f"Keep pane alive: {plan.keep_alive}",
    ]
    if plan.compose is None:
        lines.append(f"Container restart: {plan.restart_container}")
    else:
        lines.extend(
            (
                f"Compose file: {plan.compose.file}",
                f"Compose project: {plan.compose.project_name}",
                f"Compose wait timeout: {plan.compose.wait_timeout_seconds}s",
                "Compose environment keys: "
                + (", ".join(key for key, _ in plan.compose.environment) or "none"),
            )
        )
    lines.extend(
        f"Window {instance.name}: "
        + (
            f"service={instance.service}"
            if plan.compose is not None
            else f"container={instance.container}"
        )
        + " -> "
        + ", ".join(group.name for group in instance.groups)
        for instance in plan.instances
    )
    return tuple(lines)
