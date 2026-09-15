"""Execute configured project build scripts directly on the host."""

from __future__ import annotations

import subprocess

from ...builds.models import BuildPlan, BuildResult
from ...errors import BackendUnavailableError, BuildExecutionError
from ...execution import CommandRunner, SubprocessRunner


class HostBuildBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def execute(self, plan: BuildPlan) -> BuildResult:
        try:
            result = self.runner.run(
                plan.command,
                cwd=plan.workdir,
                environment=dict(plan.environment),
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
