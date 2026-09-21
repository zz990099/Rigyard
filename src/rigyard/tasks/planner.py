"""Turn a resolved task definition into a deterministic container execution plan."""

from __future__ import annotations

from ..execution.docker_exec import docker_exec_command
from .models import TaskPlan, TaskSpec


class TaskPlanner:
    def create_plan(self, task_name: str, spec: TaskSpec) -> TaskPlan:
        command = docker_exec_command(
            container=spec.container,
            program=(*spec.interpreter, str(spec.script)),
            interpreter=spec.interpreter,
            setup=spec.setup,
            workdir=spec.workdir,
            user=spec.user,
            environment=spec.environment,
            tty=spec.tty,
        )
        return TaskPlan(
            task_name=task_name,
            container=spec.container,
            script=spec.script,
            command=command,
            workdir=spec.workdir,
            user=spec.user,
            setup=spec.setup,
            environment=tuple(sorted(spec.environment.items())),
            environment_overrides=tuple(sorted(spec.environment)),
            timeout_seconds=spec.timeout_seconds,
            tty=spec.tty,
            start_container=spec.start_container,
        )
