"""Stable custom task plan rendering shared by CLI and menu."""

from __future__ import annotations

from ..tasks.models import TaskPlan
from .command_output import describe_container_command
from .style import Line, field


def describe_task(plan: TaskPlan) -> tuple[Line, ...]:
    return describe_container_command(plan, (field("Task", plan.task_name),))
