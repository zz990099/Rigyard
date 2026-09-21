"""Shared application use case for CLI and menu container creation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..containers.backend import ContainerBackend
from ..containers.models import ContainerCreateResult, ContainerRunPlan, ContainerSpec
from ..containers.planner import ContainerRunPlanner
from ..containers.service import ContainerCreateService
from ..errors import SchemaValidationError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .definitions import find_definition
from .parameters import resolve_template
from .project import project_context
from .requests import ResolutionRequest


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
        )
        config = project.config
        match = find_definition(
            config,
            "containers",
            container_name,
            request.source_path,
            project.config_path,
        )
        if match is None:
            raise SchemaValidationError(f"unknown container {container_name!r}")
        host_environment = dict(project.environment)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                host_environment,
                now=project.timestamp,
                config_path=project.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        spec, _ = resolve_template(
            config,
            match.value,
            request,
            f"containers.{container_name}",
            ContainerSpec,
            renderer,
            self.sources,
            self.formatter,
        )
        return ContainerRunPlanner().plan(
            container_name,
            spec,
            project.config_path,
            host_environment,
        )

    def execute(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.service.create(plan)
