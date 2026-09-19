"""Turn a resolved test definition into a deterministic container execution plan."""

from __future__ import annotations

import shlex

from .models import TestAction, TestActionSpec, TestPlan, TestSpec


class TestPlanner:
    def create_plan(
        self,
        test_name: str,
        action: TestAction,
        spec: TestSpec,
    ) -> TestPlan:
        action_spec = spec.run if action == "run" else spec.report
        docker = ["docker", "exec"]
        if spec.user is not None:
            docker.append(f"--user={spec.user}")
        if spec.workdir is not None:
            docker.append(f"--workdir={spec.workdir}")
        docker.extend(f"--env={name}={value}" for name, value in sorted(spec.environment.items()))
        docker.append(spec.container)
        return TestPlan(
            test_name=test_name,
            action=action,
            container=spec.container,
            script=action_spec.script,
            command=(*docker, *_container_command(action_spec, spec.setup)),
            workdir=spec.workdir,
            user=spec.user,
            setup=spec.setup,
            environment=tuple(sorted(spec.environment.items())),
            environment_overrides=tuple(sorted(spec.environment)),
            timeout_seconds=action_spec.timeout_seconds,
        )


def _container_command(
    action: TestActionSpec,
    setup: tuple[str, ...],
) -> tuple[str, ...]:
    base = (*action.interpreter, str(action.script))
    if not setup:
        return base
    prelude = " && ".join(f". {shlex.quote(script)}" for script in setup)
    program = f"{prelude} && exec {shlex.join(base)}"
    return (*action.interpreter, "-c", program)
