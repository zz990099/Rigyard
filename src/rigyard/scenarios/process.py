"""Derive the container-side argv for one scenario group process."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping

from ..errors import ScenarioPlanError
from .models import ScenarioGroupPlan, ScenarioGroupSpec

ScenarioGroup = ScenarioGroupSpec | ScenarioGroupPlan
EXIT_MARKER = "[rigyard] {group} exited with code "
SHELL_EXIT_MARKER = "[rigyard] {group} container shell exited with code "
HOST_SHELL = "/bin/sh"


def process_argv(group: ScenarioGroup) -> tuple[str, ...]:
    """Return the argv executed inside the container for one scenario group."""

    base = _base_argv(group)
    setup = tuple(group.setup)
    if not setup:
        return base
    prelude = " && ".join(f". {shlex.quote(script)}" for script in setup)
    program = f"{prelude} && exec {shlex.join(base)}"
    return (*group.interpreter, "-c", program)


def container_session_argv(group: ScenarioGroup) -> tuple[str, ...]:
    """Run one group and stay in a shell that already sourced the group setup.

    The group process runs as a child instead of replacing the shell, so the pane
    keeps a ready shell after the process stops (``Ctrl+C`` included): the same
    ``setup`` scripts stay sourced and the reported exit code is the process one.
    The command line is appended to the shell history file first, so the shell the
    pane hands over to can recall it with the up arrow, like a typed command.
    """

    shell = group.interpreter[0]
    lines = []
    if group.setup:
        lines.append(" && ".join(f". {shlex.quote(script)}" for script in group.setup))
    lines.extend(
        (
            "set +e",
            shlex.join(_base_argv(group)),
            "__rigyard_status=$?",
            f'echo "{EXIT_MARKER.format(group=_label(group))}$__rigyard_status"',
            # Same effect as typing the command into an interactive shell (legacy):
            # seed the history file so ↑ recalls it after the shell has started.
            '__rigyard_history="${HISTFILE-$HOME/.bash_history}"',
            'if [ -n "$__rigyard_history" ]; then',
            "  printf '%s\\n' "
            f"{shlex.quote(command_line(group))} >> \"$__rigyard_history\" 2>/dev/null",
            "fi",
            f"exec {shlex.join((shell, '-i'))}",
        )
    )
    return (*group.interpreter, "-c", "\n".join(lines))


def command_line(group: ScenarioGroup) -> str:
    """The group command as a user would have typed it, setup sources included."""

    sources = [f". {script}" for script in group.setup]
    return "; ".join((*sources, shlex.join(_base_argv(group))))


def host_shell_argv(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Interactive host shell the pane falls back to after the container shell."""

    for candidate in (environment.get("SHELL"), "/bin/bash", "/bin/sh"):
        if candidate and os.access(candidate, os.X_OK):
            return (candidate, "-i")
    return (HOST_SHELL, "-i")


def keep_alive_argv(
    primary: tuple[str, ...],
    group_name: str,
    host_shell: tuple[str, ...],
) -> tuple[str, ...]:
    """Wrap one pane so it stays usable after its container shell exits.

    The wrapper runs on the host on purpose: ``Ctrl+C`` reaches the pane's
    foreground process group, which would kill the ``docker exec`` client and
    turn the pane into a dead one before any container-side fallback could run.
    Ignoring SIGINT here keeps the pane alive and hands it over to an interactive
    host shell, so leaving the container shell does not kill the pane.
    """

    program = "\n".join(
        (
            'trap "" INT',
            shlex.join(primary),
            "__rigyard_status=$?",
            f'echo "{SHELL_EXIT_MARKER.format(group=group_name)}$__rigyard_status"',
            # The ignored SIGINT disposition survives exec, so reset it before
            # handing the pane to an interactive host shell.
            "trap - INT",
            f"exec {shlex.join(host_shell)}",
        )
    )
    return (HOST_SHELL, "-c", program)


def startup_exit_code(content: str, group_name: str) -> int | None:
    """Read the exit code a keep-alive pane reported for one finished group."""

    prefix = EXIT_MARKER.format(group=group_name)
    for line in content.splitlines():
        index = line.find(prefix)
        if index < 0:
            continue
        value = line[index + len(prefix) :].strip()
        if value.isdigit():
            return int(value)
    return None


def _base_argv(group: ScenarioGroup) -> tuple[str, ...]:
    if group.command is not None:
        return tuple(group.command)
    if group.script is not None:
        return (*group.interpreter, group.script)
    raise ScenarioPlanError(f"{_label(group)!r} has neither script nor command")


def _label(group: ScenarioGroup) -> str:
    return getattr(group, "name", "scenario group")
