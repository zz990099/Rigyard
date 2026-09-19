"""Execute configured project builds inside an existing Docker container."""

from __future__ import annotations

from ...builds.models import BuildPlan, BuildResult
from ...errors import BuildExecutionError
from ...execution import CommandRunner
from .exec_backend import DockerExecError, DockerExecExecutor


class DockerExecBuildBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.executor = DockerExecExecutor(runner)

    def execute(self, plan: BuildPlan) -> BuildResult:
        try:
            self.executor.execute(
                container=plan.container,
                command=plan.command,
                action_label=f"build {plan.build_name!r}",
                unavailable_label=f"build {plan.build_name!r}",
                timeout_seconds=plan.timeout_seconds,
            )
        except DockerExecError as exc:
            raise BuildExecutionError(str(exc)) from exc
        return BuildResult(plan.build_name, plan.command)
