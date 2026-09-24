"""Shared application use case for configured project builds."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..builds.backend import BuildBackend
from ..builds.models import BuildPlan, BuildResult, BuildSpec
from ..builds.planner import BuildPlanner
from ..builds.service import BuildService
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from .project import project_context
from .requests import ResolutionRequest
from .resolution import resolve_definition


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
        spec = resolve_definition(
            project,
            request,
            "builds",
            build_name,
            BuildSpec,
            sources=self.sources,
            formatter=self.formatter,
        )
        return BuildPlanner().create_plan(
            build_name,
            spec,
        )

    def execute(self, plan: BuildPlan) -> BuildResult:
        return self.service.execute(plan)
