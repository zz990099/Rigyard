"""Stable custom task plan rendering shared by CLI and menu."""

from __future__ import annotations

import shlex

from ..tasks.models import TaskPlan
from .command_output import redact_environment_values
from .style import Line, field, line


def describe_task(plan: TaskPlan) -> tuple[Line, ...]:
    lines = (
        field("Task", plan.task_name),
        field("Container", plan.container),
        field("Start stopped container", str(plan.start_container).lower()),
        field(
            "Working directory",
            str(plan.workdir) if plan.workdir is not None else "(container default)",
        ),
        field("Command", shlex.join(redact_environment_values(plan.command))),
        line(
            ("label", "Environment overrides"),
            ": ",
            ("muted", ", ".join(plan.environment_overrides) or "none"),
        ),
    )
    if plan.setup:
        lines = (*lines, field("Setup", ", ".join(plan.setup)))
    if plan.timeout_seconds is None:
        return lines
    return (*lines, field("Timeout", f"{plan.timeout_seconds} seconds"))
