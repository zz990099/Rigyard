"""Derive the container-side argv for one scenario group process."""

from __future__ import annotations

import shlex

from ..errors import ScenarioPlanError
from .models import ScenarioGroupPlan, ScenarioGroupSpec

ScenarioGroup = ScenarioGroupSpec | ScenarioGroupPlan
EXIT_MARKER = "[toolchain] {group} exited with code "
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


def keep_alive_argv(
    primary: tuple[str, ...],
    fallback: tuple[str, ...],
    group_name: str,
) -> tuple[str, ...]:
    """Wrap one pane so it stays usable after its process exits.

    The wrapper runs on the host on purpose: ``Ctrl+C`` reaches the pane's
    foreground process group, which would kill the ``docker exec`` client and
    turn the pane into a dead one before any container-side fallback could run.
    Ignoring SIGINT here keeps the pane alive, reports why the process stopped,
    and then hands the pane over to an interactive container shell.
    """

    program = "\n".join(
        (
            'trap "" INT',
            shlex.join(primary),
            "__toolchain_status=$?",
            f'echo "{EXIT_MARKER.format(group=group_name)}$__toolchain_status"',
            shlex.join(fallback),
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
