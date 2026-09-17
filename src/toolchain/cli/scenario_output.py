"""Stable scenario plan rendering shared by direct CLI and menu."""

from __future__ import annotations

from ..scenarios.models import ScenarioPlan


def describe_scenario(plan: ScenarioPlan) -> tuple[str, ...]:
    lines = [
        f"Scenario: {plan.scene_name}",
        f"Profile: {plan.profile_name}",
        "Runtime: tmux in existing containers",
        "Instances: " + ", ".join(instance.name for instance in plan.instances),
        f"tmux session: {plan.session}",
        f"Attach after start: {plan.attach}",
        f"Replace existing: {plan.replace}",
        f"Container restart: {plan.restart_container}",
        f"Mouse mode: {'on' if plan.mouse else 'off'}",
        f"Keep pane alive: {plan.keep_alive}",
    ]
    lines.extend(
        f"Window {instance.name}: {instance.container} -> "
        + ", ".join(group.name for group in instance.groups)
        for instance in plan.instances
    )
    return tuple(lines)
