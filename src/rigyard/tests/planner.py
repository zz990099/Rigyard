"""Turn a resolved test definition into a deterministic container execution plan."""

from __future__ import annotations

from ..execution.docker_exec import docker_exec_command
from .models import TestAction, TestPlan, TestSpec


class TestPlanner:
    def create_plan(
        self,
        test_name: str,
        action: TestAction,
        spec: TestSpec,
    ) -> TestPlan:
        action_spec = spec.run if action == "run" else spec.report
        command = docker_exec_command(
            container=spec.container,
            program=(*action_spec.interpreter, str(action_spec.script)),
            interpreter=action_spec.interpreter,
            setup=spec.setup,
            workdir=spec.workdir,
            user=spec.user,
            environment=spec.environment,
            tty=spec.tty,
        )
        return TestPlan(
            test_name=test_name,
            action=action,
            container=spec.container,
            script=action_spec.script,
            command=command,
            workdir=spec.workdir,
            user=spec.user,
            setup=spec.setup,
            environment=tuple(sorted(spec.environment.items())),
            environment_overrides=tuple(sorted(spec.environment)),
            timeout_seconds=action_spec.timeout_seconds,
            tty=spec.tty,
            start_container=spec.start_container,
        )
