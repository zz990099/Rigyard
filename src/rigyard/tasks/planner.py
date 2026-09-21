"""Turn a resolved task definition into a deterministic container execution plan."""

from __future__ import annotations

import shlex

from .models import TaskPlan, TaskSpec


class TaskPlanner:
    def create_plan(self, task_name: str, spec: TaskSpec) -> TaskPlan:
        docker = ["docker", "exec"]
        if spec.tty == "always":
            docker.append("--tty")
        if spec.user is not None:
            docker.append(f"--user={spec.user}")
        if spec.workdir is not None:
            docker.append(f"--workdir={spec.workdir}")
        docker.extend(f"--env={name}={value}" for name, value in sorted(spec.environment.items()))
        docker.append(spec.container)
        return TaskPlan(
            task_name=task_name,
            container=spec.container,
            script=spec.script,
            command=(*docker, *_container_command(spec)),
            workdir=spec.workdir,
            user=spec.user,
            setup=spec.setup,
            environment=tuple(sorted(spec.environment.items())),
            environment_overrides=tuple(sorted(spec.environment)),
            timeout_seconds=spec.timeout_seconds,
            tty=spec.tty,
            start_container=spec.start_container,
        )


def _container_command(spec: TaskSpec) -> tuple[str, ...]:
    base = (*spec.interpreter, str(spec.script))
    if not spec.setup:
        return base
    prelude = " && ".join(f". {shlex.quote(script)}" for script in spec.setup)
    program = f"{prelude} && exec {shlex.join(base)}"
    return (*spec.interpreter, "-c", program)
