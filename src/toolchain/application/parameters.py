"""Application use cases for project validation and parameter resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.loader import load_config, load_values
from ..config.models import ToolchainConfig
from ..parameters.context import ResolvedContext
from ..parameters.resolver import ParameterEngine
from .requests import ParameterRequest


class ValidateConfigUseCase:
    def execute(self, config_path: str | Path) -> ToolchainConfig:
        config = load_config(config_path)
        ParameterEngine(config.parameter_schema())
        return config


class InspectParametersUseCase:
    def execute(self, config_path: str | Path) -> dict[str, Any]:
        config = ValidateConfigUseCase().execute(config_path)
        return ParameterEngine(config.parameter_schema()).inspect()


class ResolveParametersUseCase:
    def execute(
        self,
        request: ParameterRequest,
        *,
        allow_missing: bool = False,
    ) -> ResolvedContext:
        config = load_config(request.config_path)
        return resolve_loaded_parameters(config, request, allow_missing=allow_missing)


def resolve_loaded_parameters(
    config: ToolchainConfig,
    request: ParameterRequest,
    *,
    allow_missing: bool = False,
) -> ResolvedContext:
    values = load_values(request.values_path) if request.values_path else {}
    return ParameterEngine(config.parameter_schema()).resolve(
        values=values,
        overrides=request.overrides,
        interactive=request.interactive,
        input_fn=request.input_fn,
        allow_missing=allow_missing,
    )

