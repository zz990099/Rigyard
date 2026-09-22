"""Stable test command plan rendering shared by CLI and menu."""

from __future__ import annotations

from ..tests.models import TestPlan
from .command_output import describe_container_command
from .style import Line, field


def describe_test(plan: TestPlan) -> tuple[Line, ...]:
    return describe_container_command(
        plan,
        (field("Test", plan.test_name), field("Action", plan.action)),
    )
