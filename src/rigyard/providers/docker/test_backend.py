"""Execute user-defined test commands inside an existing Docker container."""

from __future__ import annotations

from ...errors import TestExecutionError
from ...execution import CommandRunner
from ...tests.models import TestPlan, TestResult
from .exec_backend import DockerExecError, DockerExecExecutor


class DockerExecTestBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.executor = DockerExecExecutor(runner)

    def execute(self, plan: TestPlan) -> TestResult:
        label = f"test {plan.test_name!r} {plan.action}"
        try:
            self.executor.execute(
                container=plan.container,
                command=plan.command,
                action_label=label,
                unavailable_label=label,
                timeout_seconds=plan.timeout_seconds,
                tty=plan.tty,
            )
        except DockerExecError as exc:
            raise TestExecutionError(str(exc)) from exc
        return TestResult(plan.test_name, plan.action, plan.command)
