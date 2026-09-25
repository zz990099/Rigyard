"""Redact sensitive values from command lines rendered to users."""

from __future__ import annotations

import shlex

from ..container_commands.models import ContainerCommandPlan
from .style import Line, field, line


def redact_environment_values(command: tuple[str, ...]) -> tuple[str, ...]:
    """Replace values in Docker-style environment arguments."""

    redacted: list[str] = []
    for argument in command:
        if argument.startswith("--env="):
            name, separator, _ = argument.removeprefix("--env=").partition("=")
            if separator:
                argument = f"--env={name}=REDACTED"
        redacted.append(argument)
    return tuple(redacted)


def describe_container_command(
    plan: ContainerCommandPlan,
    identity: tuple[Line, ...],
) -> tuple[Line, ...]:
    """Render fields shared by build, test, and task execution plans."""

    lines = (
        *identity,
        field("Container", plan.container),
        field("Start stopped container", str(plan.start_container).lower()),
        field(
            "Working directory",
            str(plan.workdir) if plan.workdir is not None else "(container default)",
        ),
        field("Command", shlex.join(redact_environment_values(plan.command))),
        line(
            ("label", "Environment overrides"),
            ": ",
            ("muted", ", ".join(plan.environment_overrides) or "none"),
        ),
    )
    if plan.setup:
        lines = (*lines, field("Setup", ", ".join(plan.setup)))
    if plan.timeout_seconds is not None:
        lines = (*lines, field("Timeout", f"{plan.timeout_seconds} seconds"))
    return lines
