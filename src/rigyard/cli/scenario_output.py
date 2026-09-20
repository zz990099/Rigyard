"""Stable scenario plan rendering shared by direct CLI and menu."""

from __future__ import annotations

from ..scenarios.models import ScenarioPlan, ScenarioStartupPlan
from .style import Line, field, line


def describe_scenario_target(plan: ScenarioPlan) -> tuple[Line, ...]:
    """Short rendering for scene management actions such as stop and down."""

    return (
        field("Scenario", plan.scene_name),
        field("Profile", plan.profile_name),
        field("tmux session", plan.session),
        field("Instances", ", ".join(instance.name for instance in plan.instances)),
    )


def describe_scenario(plan: ScenarioPlan) -> tuple[Line, ...]:
    lines: list[Line] = [
        field("Scenario", plan.scene_name),
        field("Profile", plan.profile_name),
        field(
            "Runtime",
            "tmux in "
            + (
                "Compose-managed containers"
                if plan.compose is not None
                else "existing containers"
            ),
        ),
        field("Instances", ", ".join(instance.name for instance in plan.instances)),
        field("tmux session", plan.session),
        field("Attach after start", str(plan.attach)),
        field("Replace existing", str(plan.replace)),
        field("Mouse mode", "on" if plan.mouse else "off"),
        field("Keep pane alive", str(plan.keep_alive)),
        field("Window startup", _startup_label(plan.startup, "windows")),
    ]
    if plan.compose is None:
        lines.append(field("Container restart", plan.restart_container))
    else:
        lines.extend(
            (
                field("Compose file", str(plan.compose.file)),
                field("Compose project", plan.compose.project_name),
                field(
                    "Compose wait timeout",
                    f"{plan.compose.wait_timeout_seconds}s",
                ),
                line(
                    ("label", "Compose environment keys"),
                    ": ",
                    ("muted", ", ".join(key for key, _ in plan.compose.environment) or "none"),
                ),
            )
        )
    for instance in plan.instances:
        lines.append(
            line(
                ("label", f"Window {instance.name}"),
                ": ",
                ("muted", "service=" if plan.compose is not None else "container="),
                (
                    "value",
                    (instance.service if plan.compose is not None else instance.container) or "",
                ),
                ("muted", " -> "),
                ("value", ", ".join(group.name for group in instance.groups)),
            )
        )
        lines.append(
            field(
                f"Pane startup {instance.name}",
                _startup_label(instance.startup, "panes"),
            )
        )
    return tuple(lines)


def _startup_label(startup: ScenarioStartupPlan, noun: str) -> str:
    if startup.mode == "parallel":
        return "parallel"
    return f"sequential ({startup.interval_seconds}s between {noun})"
