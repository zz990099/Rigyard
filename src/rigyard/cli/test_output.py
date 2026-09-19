"""Stable test command plan rendering shared by CLI and menu."""

from __future__ import annotations

import shlex

from ..tests.models import TestPlan
from .style import Line, field, line


def describe_test(plan: TestPlan) -> tuple[Line, ...]:
    lines = (
        field("Test", plan.test_name),
        field("Action", plan.action),
        field("Container", plan.container),
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
