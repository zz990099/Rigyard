"""Shared application use case for configured project builds."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..builds.backend import BuildBackend
from ..builds.models import BuildPlan, BuildResult, BuildSpec
from ..builds.planner import BuildPlanner
from ..builds.service import BuildService
from ..errors import SchemaValidationError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .definitions import find_definition
from .parameters import resolve_template
from .project import project_context
from .requests import ResolutionRequest


class BuildProjectUseCase:
    def __init__(
        self,
        backend: BuildBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.service = BuildService(backend)
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        build_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> BuildPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
        )
        config = project.config
        match = find_definition(
            config,
            "builds",
            build_name,
            request.source_path,
            project.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.builds)) or "none"
            raise SchemaValidationError(
                f"unknown build {build_name!r}; configured builds: {available}"
            )
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                project.environment,
                now=project.timestamp,
                config_path=project.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        spec, _ = resolve_template(
            config,
            match.value,
            request,
            f"builds.{build_name}",
            BuildSpec,
            renderer,
            self.sources,
            self.formatter,
            environment=project.environment,
        )
        return BuildPlanner().create_plan(
            build_name,
            spec,
        )

    def execute(self, plan: BuildPlan) -> BuildResult:
        return self.service.execute(plan)
