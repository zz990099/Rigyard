"""Stable project build plan rendering shared by CLI and menu."""

from __future__ import annotations

from ..builds.models import BuildPlan
from .command_output import describe_container_command
from .style import Line, field


def describe_build(plan: BuildPlan) -> tuple[Line, ...]:
    return describe_container_command(plan, (field("Build", plan.build_name),))
