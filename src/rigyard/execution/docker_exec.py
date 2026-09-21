"""Shared planning helpers for commands executed in Docker containers."""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence

from .tty import TtyMode


def docker_exec_command(
    *,
    container: str,
    program: Sequence[str],
    interpreter: tuple[str, ...],
    setup: tuple[str, ...] = (),
    workdir: object | None = None,
    user: str | None = None,
    environment: Mapping[str, str] | None = None,
    tty: TtyMode = "auto",
) -> tuple[str, ...]:
    """Build one deterministic ``docker exec`` argv tuple."""

    docker = ["docker", "exec"]
    if tty == "always":
        docker.append("--tty")
    if user is not None:
        docker.append(f"--user={user}")
    if workdir is not None:
        docker.append(f"--workdir={workdir}")
    docker.extend(
        f"--env={name}={value}" for name, value in sorted((environment or {}).items())
    )
    docker.append(container)
    return (*docker, *_container_command(program, interpreter, setup))


def _container_command(
    program: Sequence[str],
    interpreter: tuple[str, ...],
    setup: tuple[str, ...],
) -> tuple[str, ...]:
    argv = tuple(program)
    if not setup:
        return argv
    prelude = " && ".join(f". {shlex.quote(script)}" for script in setup)
    return (*interpreter, "-c", f"{prelude} && exec {shlex.join(argv)}")
