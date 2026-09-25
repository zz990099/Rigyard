"""Low-level tmux operations for scenario execution."""

from __future__ import annotations

import sys
from collections.abc import Mapping

from ..execution import CommandResult, CommandRunner
from .runtime import ScenarioCommandGateway

PLACEHOLDER = "import time; time.sleep(86400)"
PANE_GROUP_OPTION = "@rigyard_group"
PANE_BORDER_FORMAT = f"#{{pane_index}}: #{{{PANE_GROUP_OPTION}}}"


class TmuxSessionBackend:
    """Own tmux session, window, and pane commands without scenario policy."""

    def __init__(
        self,
        commands: ScenarioCommandGateway,
        runner: CommandRunner,
        environment: Mapping[str, str],
    ) -> None:
        self.commands = commands
        self.runner = runner
        self.environment = environment

    def require(self) -> None:
        self.commands.require(("tmux", "-V"), "tmux")

    def session_exists(self, session: str) -> bool:
        return self.commands.session_exists(session)

    def window_exists(self, session: str, window_name: str) -> bool:
        return self.commands.window_exists(session, window_name)

    def panes(self, window: str) -> tuple[tuple[str, int], ...]:
        return self.commands.panes(window, PANE_GROUP_OPTION)

    def create_window(self, session: str, window_name: str) -> bool:
        created_session = not self.session_exists(session)
        if created_session:
            create = ("tmux", "new-session", "-d", "-s", session, "-n", window_name)
        else:
            create = ("tmux", "new-window", "-d", "-t", session, "-n", window_name)
        self.commands.checked(
            (*create, sys.executable, "-c", PLACEHOLDER),
            f"cannot create tmux window {window_name!r}",
        )
        return created_session

    def configure_session(self, session: str, *, mouse: bool) -> None:
        self._sync_environment(session)
        self.commands.checked(
            ("tmux", "set-option", "-t", session, "mouse", "on" if mouse else "off"),
            "cannot configure tmux mouse mode",
        )

    def configure_window(self, window: str) -> None:
        for command, message in (
            (("set-option", "-w", "-t", window, "remain-on-exit", "on"), "remain-on-exit"),
            (("set-option", "-w", "-t", window, "pane-border-status", "top"), "pane border"),
            (
                ("set-option", "-w", "-t", window, "pane-border-format", PANE_BORDER_FORMAT),
                "pane border format",
            ),
        ):
            self.commands.checked(("tmux", *command), f"cannot configure tmux {message}")

    def split_window(self, window: str, window_name: str) -> None:
        self.commands.checked(
            (
                "tmux",
                "split-window",
                "-d",
                "-t",
                window,
                sys.executable,
                "-c",
                PLACEHOLDER,
            ),
            f"cannot split tmux window {window_name!r}",
        )
        # Re-tiling prevents repeated splits from exhausting a small pane.
        self.tile(window, window_name)

    def tile(self, window: str, window_name: str) -> None:
        self.commands.checked(
            ("tmux", "select-layout", "-t", window, "tiled"),
            f"cannot lay out tmux window {window_name!r}",
        )

    def start_pane(
        self,
        target: str,
        command: tuple[str, ...],
        group_name: str,
    ) -> None:
        self.commands.checked(
            ("tmux", "respawn-pane", "-k", "-t", target, *command),
            f"cannot start tmux pane {group_name!r}",
        )
        self.commands.checked(
            ("tmux", "set-option", "-p", "-t", target, PANE_GROUP_OPTION, group_name),
            f"cannot tag tmux pane {group_name!r}",
        )
        self.commands.checked(
            ("tmux", "select-pane", "-t", target, "-T", group_name),
            f"cannot title tmux pane {group_name!r}",
        )

    def interrupt(self, target: str) -> None:
        self.runner.run(("tmux", "send-keys", "-t", target, "C-c"), capture=True)

    def kill_session(self, session: str, *, checked: bool = True) -> None:
        command = ("tmux", "kill-session", "-t", session)
        if checked:
            self.commands.checked(command, f"cannot stop tmux session {session!r}")
        else:
            self.runner.run(command, capture=True)

    def kill_window(self, window: str, window_name: str, *, checked: bool = True) -> None:
        command = ("tmux", "kill-window", "-t", window)
        if checked:
            self.commands.checked(command, f"cannot stop tmux window {window_name!r}")
        else:
            self.runner.run(command, capture=True)

    def status(self, session: str, window: str | None = None) -> CommandResult:
        return self.commands.checked(
            (
                "tmux",
                "list-panes",
                *(("-s",) if window is None else ()),
                "-t",
                session if window is None else f"{session}:{window}",
                "-F",
                "#{window_name}.#{pane_index} #{pane_title} "
                "dead=#{pane_dead} exit=#{pane_exit_status}",
            ),
            f"cannot inspect tmux session {session!r}",
        )

    def select_window(self, window: str, window_name: str) -> None:
        self.commands.checked(
            ("tmux", "select-window", "-t", window),
            f"cannot select tmux window {window_name!r}",
        )

    def select_pane(self, target: str, group_name: str) -> None:
        self.commands.checked(
            ("tmux", "select-pane", "-t", target),
            f"cannot select tmux pane {group_name!r}",
        )

    def attach(self, session: str) -> None:
        attach_command = "switch-client" if self.environment.get("TMUX") else "attach-session"
        self.commands.checked(
            ("tmux", attach_command, "-t", session),
            f"cannot attach tmux session {session!r}",
            capture=False,
        )

    def capture(self, target: str, message: str) -> CommandResult:
        return self.commands.checked(
            ("tmux", "capture-pane", "-p", "-t", target, "-S", "-"),
            message,
        )

    def startup_state(self, target: str, title: str) -> CommandResult:
        return self.commands.checked(
            ("tmux", "display-message", "-p", "-t", target, "#{pane_dead} #{pane_exit_status}"),
            f"cannot inspect startup of group {title!r}",
        )

    def _sync_environment(self, session: str) -> None:
        # A persistent tmux server may have stale PATH or Docker connection settings.
        for key in (
            "PATH",
            "HOME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        ):
            command: tuple[str, ...] = ("tmux", "set-environment", "-t", session)
            if key in self.environment:
                command = (*command, key, self.environment[key])
            else:
                command = (*command, "-r", key)
            self.commands.checked(command, f"cannot configure tmux environment {key!r}")
