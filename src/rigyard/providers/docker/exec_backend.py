"""Shared Docker exec process execution for container-backed features."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

from ...errors import BackendUnavailableError
from ...execution import (
    CommandRunner,
    SubprocessRunner,
    TtyMode,
    cancel_docker_exec,
    cancellable_docker_exec,
)


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
        start_container: bool = True,
    ) -> None:
        self._ensure_container(container, start_container=start_container)
        if tty == "auto" and self.is_terminal():
            command = _with_tty(command)
        invocation = cancellable_docker_exec(command, container)
        try:
            result = self.runner.run(
                invocation.command,
                capture=False,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            cancellation_error = cancel_docker_exec(self.runner, invocation.cancel_command)
            suffix = f"; {cancellation_error}" if cancellation_error else ""
            raise DockerExecError(
                f"{action_label} timed out after {timeout_seconds} seconds{suffix}"
            ) from exc
        except KeyboardInterrupt as exc:
            cancellation_error = cancel_docker_exec(self.runner, invocation.cancel_command)
            if cancellation_error:
                raise DockerExecError(
                    f"{action_label} was interrupted; {cancellation_error}"
                ) from exc
            raise
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute {unavailable_label}: {exc}") from exc
        if result.returncode:
            raise DockerExecError(f"{action_label} failed with exit code {result.returncode}")

    def _ensure_container(self, container: str, *, start_container: bool) -> None:
        if self._container_running(container):
            return
        if not start_container:
            raise DockerExecError(
                f"container {container!r} is not running; start it before executing commands"
            )
        try:
            result = self.runner.run(("docker", "start", container), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute Docker: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else f" (exit {result.returncode})"
            raise DockerExecError(f"cannot start container {container!r}{suffix}")
        if not self._container_running(container):
            raise DockerExecError(
                f"container {container!r} did not remain running after docker start"
            )

    def _container_running(self, container: str) -> bool:
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
        return result.stdout.strip() == "true"


def _stdout_is_terminal() -> bool:
    isatty = getattr(sys.stdout, "isatty", None)
    return bool(isatty is not None and isatty())


def _with_tty(command: tuple[str, ...]) -> tuple[str, ...]:
    if command[:2] != ("docker", "exec") or "--tty" in command[2:]:
        return command
    return (*command[:2], "--tty", *command[2:])
