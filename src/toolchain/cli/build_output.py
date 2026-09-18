"""Stable project build plan rendering shared by CLI and menu."""

from __future__ import annotations

import shlex

from ..builds.models import BuildPlan


def describe_build(plan: BuildPlan) -> tuple[str, ...]:
    lines = (
        f"Build: {plan.build_name}",
        f"Container: {plan.container}",
        "Working directory: "
        + (str(plan.workdir) if plan.workdir is not None else "(container default)"),
        f"Command: {shlex.join(plan.command)}",
        "Environment overrides: " + (", ".join(plan.environment_overrides) or "none"),
    )
    if plan.setup:
        lines = (*lines, "Setup: " + ", ".join(plan.setup))
    if plan.timeout_seconds is None:
        return lines
    return (*lines, f"Timeout: {plan.timeout_seconds} seconds")
