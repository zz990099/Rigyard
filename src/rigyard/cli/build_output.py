"""Stable project build plan rendering shared by CLI and menu."""

from __future__ import annotations

import shlex

from ..builds.models import BuildPlan
from .style import Line, field, line


def describe_build(plan: BuildPlan) -> tuple[Line, ...]:
    lines = (
        field("Build", plan.build_name),
        field("Container", plan.container),
        field("Start stopped container", str(plan.start_container).lower()),
        field(
            "Working directory",
            str(plan.workdir) if plan.workdir is not None else "(container default)",
        ),
        field("Command", shlex.join(plan.command)),
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
