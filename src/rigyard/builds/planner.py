"""Turn a resolved build definition into a deterministic container execution plan."""

from __future__ import annotations

from ..container_commands import plan_container_command
from .models import BuildPlan, BuildSpec


class BuildPlanner:
    def create_plan(
        self,
        build_name: str,
        spec: BuildSpec,
    ) -> BuildPlan:
        common = plan_container_command(
            spec,
            program=(*spec.interpreter, str(spec.script)),
            interpreter=spec.interpreter,
            timeout_seconds=spec.timeout_seconds,
        )
        return BuildPlan(
            **vars(common),
            build_name=build_name,
            script=spec.script,
        )
