"""Shared Docker exec process execution for container-backed features."""

from __future__ import annotations

import subprocess

from ...errors import BackendUnavailableError
from ...execution import CommandRunner, SubprocessRunner


class DockerExecError(Exception):
    """A Docker exec operation failed after reaching the provider."""


class DockerExecExecutor:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def execute(
        self,
        *,
        container: str,
        command: tuple[str, ...],
        action_label: str,
        unavailable_label: str,
        timeout_seconds: int | None,
    ) -> None:
        self._check_container(container)
        try:
            result = self.runner.run(
                command,
                capture=False,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise DockerExecError(
                f"{action_label} timed out after {timeout_seconds} seconds"
            ) from exc
        except OSError as exc:
            raise BackendUnavailableError(
                f"cannot execute {unavailable_label}: {exc}"
            ) from exc
        if result.returncode:
            raise DockerExecError(
                f"{action_label} failed with exit code {result.returncode}"
            )

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
            raise DockerExecError(
                f"container {container!r} does not exist{suffix}; create it first"
            )
        if result.stdout.strip() != "true":
            raise DockerExecError(
                f"container {container!r} is not running; start it before executing commands"
            )
