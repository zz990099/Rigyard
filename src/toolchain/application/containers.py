"""Shared application use case for CLI and menu container creation."""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..config.loader import load_config
from ..containers.backend import ContainerBackend
from ..containers.models import ContainerCreateResult, ContainerRunPlan, ContainerSpec
from ..containers.planner import ContainerRunPlanner
from ..containers.service import ContainerCreateService
from ..errors import SchemaValidationError
from .parameters import resolve_template
from .requests import ResolutionRequest


class CreateContainerUseCase:
    def __init__(self, backend: ContainerBackend) -> None:
        self.service = ContainerCreateService(backend)

    def plan(
        self,
        container_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> ContainerRunPlan:
        config = load_config(request.config_path)
        if container_name not in config.containers:
            raise SchemaValidationError(f"unknown container {container_name!r}")
        spec, _ = resolve_template(
            config,
            config.containers[container_name],
            request,
            f"containers.{container_name}",
            ContainerSpec,
        )
        return ContainerRunPlanner().plan(
            container_name,
            spec,
            request.config_path,
            dict(os.environ if environment is None else environment),
        )

    def execute(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.service.create(plan)
