"""Turn a resolved test definition into a deterministic container execution plan."""

from __future__ import annotations

from ..container_commands import plan_container_command
from .models import TestAction, TestPlan, TestSpec


class TestPlanner:
    def create_plan(
        self,
        test_name: str,
        action: TestAction,
        spec: TestSpec,
    ) -> TestPlan:
        action_spec = spec.run if action == "run" else spec.report
        common = plan_container_command(
            spec,
            program=(*action_spec.interpreter, str(action_spec.script)),
            interpreter=action_spec.interpreter,
            timeout_seconds=action_spec.timeout_seconds,
        )
        return TestPlan(
            **vars(common),
            test_name=test_name,
            action=action,
            script=action_spec.script,
        )
