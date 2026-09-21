"""Redact sensitive values from command lines rendered to users."""

from __future__ import annotations


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
