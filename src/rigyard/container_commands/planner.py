"""Create the shared portion of a container-backed command plan."""

from __future__ import annotations

from ..execution.docker_exec import docker_exec_command
from .models import ContainerCommandPlan, ContainerCommandSpec


def plan_container_command(
    spec: ContainerCommandSpec,
    *,
    program: tuple[str, ...],
    interpreter: tuple[str, ...],
    timeout_seconds: int | None,
) -> ContainerCommandPlan:
    command = docker_exec_command(
        container=spec.container,
        program=program,
        interpreter=interpreter,
        setup=spec.setup,
        workdir=spec.workdir,
        user=spec.user,
        environment=spec.environment,
        tty=spec.tty,
    )
    return ContainerCommandPlan(
        container=spec.container,
        command=command,
        workdir=spec.workdir,
        user=spec.user,
        setup=spec.setup,
        environment=tuple(sorted(spec.environment.items())),
        environment_overrides=tuple(sorted(spec.environment)),
        timeout_seconds=timeout_seconds,
        tty=spec.tty,
        start_container=spec.start_container,
    )
