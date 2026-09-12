"""Shared application use case for CLI and menu container creation."""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..config.loader import load_config
from ..containers.backend import ContainerBackend
from ..containers.models import ContainerCreateResult, ContainerRunPlan
from ..containers.planner import ContainerRunPlanner
from ..containers.service import ContainerCreateService
from ..errors import SchemaValidationError
from .parameters import resolve_loaded_parameters
from .requests import ParameterRequest


class CreateContainerUseCase:
    def __init__(self, backend: ContainerBackend) -> None:
        self.service = ContainerCreateService(backend)

    def plan(
        self,
        container_name: str,
        request: ParameterRequest,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> ContainerRunPlan:
        config = load_config(request.config_path)
        if container_name not in config.containers:
            raise SchemaValidationError(f"unknown container {container_name!r}")
        context = resolve_loaded_parameters(config, request)
        return ContainerRunPlanner().plan(
            container_name,
            config.containers[container_name],
            context,
            request.config_path,
            dict(os.environ if environment is None else environment),
        )

    def execute(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.service.create(plan)
