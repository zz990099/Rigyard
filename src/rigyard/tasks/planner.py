"""Turn a resolved task definition into a deterministic container execution plan."""

from __future__ import annotations

from ..container_commands import plan_container_command
from .models import TaskPlan, TaskSpec


class TaskPlanner:
    def create_plan(self, task_name: str, spec: TaskSpec) -> TaskPlan:
        common = plan_container_command(
            spec,
            program=(*spec.interpreter, str(spec.script)),
            interpreter=spec.interpreter,
            timeout_seconds=spec.timeout_seconds,
        )
        return TaskPlan(
            **vars(common),
            task_name=task_name,
            script=spec.script,
        )
