"""Shared planning helpers for commands executed in Docker containers."""

from __future__ import annotations

import shlex
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .runner import CommandRunner
from .tty import TtyMode

CANCEL_TIMEOUT_SECONDS = 5

_RUN_SCRIPT = r'''marker=$1
shift
child=
grouped=0
cleanup() {
    rm -f "$marker"
}
forward() {
    [ -n "$child" ] || return 0
    if [ "$grouped" -eq 1 ]; then
        kill -TERM -"$child" 2>/dev/null || true
    else
        kill -TERM "$child" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap forward INT TERM
if command -v setsid >/dev/null 2>&1; then
    setsid "$@" &
    grouped=1
else
    "$@" &
fi
child=$!
printf '%s %s\n' "$child" "$grouped" > "$marker"
wait "$child"
status=$?
exit "$status"'''

_CANCEL_SCRIPT = r'''marker=$1
attempt=0
while [ ! -s "$marker" ] && [ "$attempt" -lt 20 ]; do
    sleep 0.05
    attempt=$((attempt + 1))
done
[ -s "$marker" ] || exit 0
read -r pid grouped < "$marker"
signal() {
    if [ "$grouped" -eq 1 ]; then
        kill -"$1" -"$pid" 2>/dev/null
    else
        kill -"$1" "$pid" 2>/dev/null
    fi
}
alive() {
    if [ "$grouped" -eq 1 ]; then
        kill -0 -"$pid" 2>/dev/null
    else
        kill -0 "$pid" 2>/dev/null
    fi
}
signal TERM || true
attempt=0
while alive && [ "$attempt" -lt 20 ]; do
    sleep 0.1
    attempt=$((attempt + 1))
done
if alive; then
    signal KILL || true
fi
rm -f "$marker"'''


@dataclass(frozen=True)
class DockerExecInvocation:
    """One attached Docker exec command and the command that cancels its process group."""

    command: tuple[str, ...]
    cancel_command: tuple[str, ...]


def cancel_docker_exec(runner: CommandRunner, command: tuple[str, ...]) -> str | None:
    """Stop a wrapped container process, returning detail only when cleanup fails."""

    try:
        result = runner.run(
            command,
            capture=True,
            timeout_seconds=CANCEL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not stop its container process: {type(exc).__name__}"
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else f" (exit {result.returncode})"
        return f"could not stop its container process{suffix}"
    return None


def docker_exec_command(
    *,
    container: str,
    program: Sequence[str],
    interpreter: tuple[str, ...],
    setup: tuple[str, ...] = (),
    workdir: str | Path | None = None,
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
    docker.extend(f"--env={name}={value}" for name, value in sorted((environment or {}).items()))
    docker.append(container)
    return (*docker, *_container_command(program, interpreter, setup))


def cancellable_docker_exec(
    command: tuple[str, ...],
    container: str,
    *,
    execution_id: str | None = None,
) -> DockerExecInvocation:
    """Wrap a Docker exec command so its container process can be stopped out of band."""

    if command[:2] != ("docker", "exec"):
        raise ValueError("cancellable Docker execution requires a docker exec command")
    try:
        container_index = command.index(container, 2)
    except ValueError as exc:
        raise ValueError(f"container {container!r} is missing from docker exec command") from exc
    program = command[container_index + 1 :]
    if not program:
        raise ValueError("docker exec command has no container program")

    token = execution_id or uuid.uuid4().hex
    marker = f"/tmp/rigyard-exec-{token}.pid"
    prefix = command[: container_index + 1]
    wrapped = (*prefix, "/bin/sh", "-c", _RUN_SCRIPT, "rigyard-exec", marker, *program)
    cancel = (
        "docker",
        "exec",
        container,
        "/bin/sh",
        "-c",
        _CANCEL_SCRIPT,
        "rigyard-cancel",
        marker,
    )
    return DockerExecInvocation(wrapped, cancel)


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
