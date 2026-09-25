"""External command gateway used by scenario orchestration."""

from __future__ import annotations

from collections.abc import Mapping

from ..errors import BackendUnavailableError, ScenarioExecutionError
from ..execution import CommandResult, CommandRunner


class ScenarioCommandGateway:
    """Translate Docker and tmux process outcomes into scenario errors."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def require(self, command: tuple[str, ...], label: str) -> None:
        try:
            result = self.runner.run(command, capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute {label}: {exc}") from exc
        if result.returncode:
            raise BackendUnavailableError(f"{label} is unavailable")

    def checked(
        self,
        command: tuple[str, ...],
        message: str,
        *,
        capture: bool = True,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        try:
            result = self.runner.run(command, capture=capture, environment=environment)
        except OSError as exc:
            raise BackendUnavailableError(f"{message}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else f" (exit {result.returncode})"
            raise ScenarioExecutionError(message + suffix)
        return result

    def container_running(self, container: str) -> bool:
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
            raise ScenarioExecutionError(
                f"container {container!r} is not available{suffix}; "
                f"create it first with 'rigyard container create {container}'"
            )
        return result.stdout.strip() == "true"

    def session_exists(self, session: str) -> bool:
        try:
            result = self.runner.run(("tmux", "has-session", "-t", session), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute tmux: {exc}") from exc
        return result.returncode == 0

    def window_exists(self, session: str, window_name: str) -> bool:
        try:
            result = self.runner.run(
                ("tmux", "list-windows", "-t", session, "-F", "#{window_name}"),
                capture=True,
            )
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute tmux: {exc}") from exc
        if result.returncode:
            return False
        return window_name in result.stdout.splitlines()

    def panes(self, window: str, group_option: str) -> tuple[tuple[str, int], ...]:
        result = self.checked(
            (
                "tmux",
                "list-panes",
                "-t",
                window,
                "-F",
                f"#{{{group_option}}} #{{pane_index}}",
            ),
            f"cannot inspect tmux window {window!r}",
        )
        panes = []
        for line in result.stdout.splitlines():
            title, _, index = line.rpartition(" ")
            panes.append((title, int(index)))
        return tuple(panes)
