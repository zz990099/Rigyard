"""Execute custom tasks inside an existing Docker container."""

from __future__ import annotations

from ...errors import TaskExecutionError
from ...execution import CommandRunner
from ...tasks.models import TaskPlan, TaskResult
from .exec_backend import DockerExecError, DockerExecExecutor


class DockerExecTaskBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.executor = DockerExecExecutor(runner)

    def execute(self, plan: TaskPlan) -> TaskResult:
        label = f"task {plan.task_name!r}"
        try:
            self.executor.execute(
                container=plan.container,
                command=plan.command,
                action_label=label,
                unavailable_label=label,
                timeout_seconds=plan.timeout_seconds,
                tty=plan.tty,
                start_container=plan.start_container,
            )
        except DockerExecError as exc:
            raise TaskExecutionError(str(exc)) from exc
        return TaskResult(plan.task_name, plan.command)
