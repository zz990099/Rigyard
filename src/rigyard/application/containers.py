"""Shared application use case for CLI and menu container creation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..containers.backend import ContainerBackend
from ..containers.models import ContainerCreateResult, ContainerRunPlan, ContainerSpec
from ..containers.planner import ContainerRunPlanner
from ..containers.service import ContainerCreateService
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from .project import project_context
from .requests import ResolutionRequest
from .resolution import resolve_definition


class CreateContainerUseCase:
    def __init__(
        self,
        backend: ContainerBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.service = ContainerCreateService(backend)
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        container_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ContainerRunPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
            workspace_root=request.workspace_root,
        )
        spec = resolve_definition(
            project,
            request,
            "containers",
            container_name,
            ContainerSpec,
            sources=self.sources,
            formatter=self.formatter,
        )
        return ContainerRunPlanner().plan(
            container_name,
            spec,
            project.config_path,
            project.environment,
        )

    def execute(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.service.create(plan)
