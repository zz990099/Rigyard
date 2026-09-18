"""Execute configured project builds inside an existing Docker container."""

from __future__ import annotations

import subprocess

from ...builds.models import BuildPlan, BuildResult
from ...errors import BackendUnavailableError, BuildExecutionError
from ...execution import CommandRunner, SubprocessRunner


class DockerExecBuildBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def execute(self, plan: BuildPlan) -> BuildResult:
        self._check_container(plan.container)
        try:
            result = self.runner.run(
                plan.command,
                capture=False,
                timeout_seconds=plan.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise BuildExecutionError(
                f"build {plan.build_name!r} timed out after {plan.timeout_seconds} seconds"
            ) from exc
        except OSError as exc:
            raise BackendUnavailableError(
                f"cannot execute build {plan.build_name!r}: {exc}"
            ) from exc
        if result.returncode:
            raise BuildExecutionError(
                f"build {plan.build_name!r} failed with exit code {result.returncode}"
            )
        return BuildResult(plan.build_name, plan.command)

    def _check_container(self, container: str) -> None:
        try:
            result = self.runner.run(
                ("docker", "inspect", "--format={{.State.Running}}", container),
                capture=True,
            )
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute Docker: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise BuildExecutionError(
                f"container {container!r} does not exist{suffix}; create it first"
            )
        if result.stdout.strip() != "true":
            raise BuildExecutionError(
                f"container {container!r} is not running; start it before building"
            )
