"""Shared application use case for configured project builds."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..builds.backend import BuildBackend
from ..builds.models import BuildPlan, BuildResult, BuildSpec
from ..builds.planner import BuildPlanner
from ..builds.service import BuildService
from ..config.loader import load_config
from ..errors import SchemaValidationError
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .definitions import find_definition
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
        now: datetime | None = None,
    ) -> BuildPlan:
        config = load_config(request.config_path)
        template = find_definition(
            config,
            "builds",
            build_name,
            request.source_path,
            request.config_path,
        )
        if template is None:
            available = ", ".join(sorted(config.builds)) or "none"
            raise SchemaValidationError(
                f"unknown build {build_name!r}; configured builds: {available}"
            )
        host_environment = dict(os.environ if environment is None else environment)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                host_environment,
                now=now,
                config_path=request.config_path,
                variables=config.variables,
            )
        )
        spec, _ = resolve_template(
            config,
            template,
            request,
            f"builds.{build_name}",
            BuildSpec,
            renderer,
        )
        return BuildPlanner().create_plan(
            build_name,
            spec,
        )

    def execute(self, plan: BuildPlan) -> BuildResult:
        return self.service.execute(plan)
