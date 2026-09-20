"""Shared Docker exec process execution for container-backed features."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

from ...errors import BackendUnavailableError
from ...execution import CommandRunner, SubprocessRunner, TtyMode


class DockerExecError(Exception):
    """A Docker exec operation failed after reaching the provider."""


class DockerExecExecutor:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        is_terminal: Callable[[], bool] | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.is_terminal = is_terminal or _stdout_is_terminal

    def execute(
        self,
        *,
        container: str,
        command: tuple[str, ...],
        action_label: str,
        unavailable_label: str,
        timeout_seconds: int | None,
        tty: TtyMode = "auto",
    ) -> None:
        self._check_container(container)
        if tty == "auto" and self.is_terminal():
            command = _with_tty(command)
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


def _stdout_is_terminal() -> bool:
    isatty = getattr(sys.stdout, "isatty", None)
    return bool(isatty is not None and isatty())


def _with_tty(command: tuple[str, ...]) -> tuple[str, ...]:
    if command[:2] != ("docker", "exec") or "--tty" in command[2:]:
        return command
    return (*command[:2], "--tty", *command[2:])
