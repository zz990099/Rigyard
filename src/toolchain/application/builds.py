"""Shared application use case for configured project builds."""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..builds.backend import BuildBackend
from ..builds.models import BuildPlan, BuildResult, BuildSpec
from ..builds.planner import BuildPlanner
from ..builds.service import BuildService
from ..config.loader import load_config
from ..errors import SchemaValidationError
from .parameters import resolve_template
from .requests import ResolutionRequest


class BuildProjectUseCase:
    def __init__(self, backend: BuildBackend) -> None:
        self.service = BuildService(backend)

    def plan(
        self,
        build_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> BuildPlan:
        config = load_config(request.config_path)
        if build_name not in config.builds:
            available = ", ".join(sorted(config.builds)) or "none"
            raise SchemaValidationError(
                f"unknown build {build_name!r}; configured builds: {available}"
            )
        spec, _ = resolve_template(
            config,
            config.builds[build_name],
            request,
            f"builds.{build_name}",
            BuildSpec,
        )
        return BuildPlanner().create_plan(
            build_name,
            spec,
            request.config_path,
            dict(os.environ if environment is None else environment),
        )

    def execute(self, plan: BuildPlan) -> BuildResult:
        return self.service.execute(plan)
