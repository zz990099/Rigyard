"""Shared application use case for CLI and menu container creation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..config.loader import load_config
from ..containers.backend import ContainerBackend
from ..containers.models import ContainerCreateResult, ContainerRunPlan, ContainerSpec
from ..containers.planner import ContainerRunPlanner
from ..containers.service import ContainerCreateService
from ..errors import SchemaValidationError
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .definitions import find_definition
from .parameters import resolve_template
from .requests import ResolutionRequest


class CreateContainerUseCase:
    def __init__(self, backend: ContainerBackend, *, sources: DynamicSources | None = None) -> None:
        self.service = ContainerCreateService(backend)
        self.sources = dict(sources or {})

    def plan(
        self,
        container_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ContainerRunPlan:
        config = load_config(request.config_path)
        template = find_definition(
            config,
            "containers",
            container_name,
            request.source_path,
            request.config_path,
        )
        if template is None:
            raise SchemaValidationError(f"unknown container {container_name!r}")
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
            f"containers.{container_name}",
            ContainerSpec,
            renderer,
            self.sources,
        )
        return ContainerRunPlanner().plan(
            container_name,
            spec,
            request.config_path,
            host_environment,
        )

    def execute(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.service.create(plan)
