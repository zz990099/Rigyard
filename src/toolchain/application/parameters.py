"""Application boundary for inline runtime value discovery and resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from ..builds.models import BuildSpec
from ..config.loader import load_config, load_values
from ..config.models import ToolchainConfig
from ..containers.models import ContainerSpec
from ..errors import ResolutionError
from ..images.models import ImageSpec
from ..parameters.context import ResolvedContext
from ..parameters.resolver import (
    RuntimeValueResolver,
    collect_prompts,
    flatten_values,
    materialize_as,
)
from .requests import ResolutionRequest

ModelT = TypeVar("ModelT", bound=BaseModel)


class ValidateConfigUseCase:
    def execute(self, config_path: str | Path) -> ToolchainConfig:
        return load_config(config_path)


class InspectParametersUseCase:
    def execute(self, config_path: str | Path) -> dict[str, Any]:
        config = load_config(config_path)
        prompts = collect_prompts(config)
        return {
            "version": config.version,
            "runtime_values": RuntimeValueResolver(prompts).inspect(),
        }


class ResolveParametersUseCase:
    def execute(
        self, request: ResolutionRequest, *, allow_missing: bool = False
    ) -> ResolvedContext:
        config = load_config(request.config_path)
        context = resolve_prompts(config, request, allow_missing=allow_missing)
        if not allow_missing:
            for name, template in config.images.items():
                materialize_as(template, f"images.{name}", context, ImageSpec)
            for name, template in config.containers.items():
                materialize_as(template, f"containers.{name}", context, ContainerSpec)
            for name, template in config.builds.items():
                materialize_as(template, f"builds.{name}", context, BuildSpec)
        return context


def resolve_prompts(
    template: BaseModel,
    request: ResolutionRequest,
    *,
    prefix: str = "",
    allow_missing: bool = False,
) -> ResolvedContext:
    prompts = collect_prompts(template, prefix)
    values = load_values(request.values_path) if request.values_path else {}
    return RuntimeValueResolver(prompts).resolve(
        values=values,
        overrides=request.overrides,
        interactive=request.interactive,
        input_fn=request.input_fn,
        allow_missing=allow_missing,
    )


def resolve_template(
    root: BaseModel,
    template: BaseModel,
    request: ResolutionRequest,
    prefix: str,
    target: type[ModelT],
) -> tuple[ModelT, ResolvedContext]:
    selected = collect_prompts(template, prefix)
    available = collect_prompts(root)
    values = load_values(request.values_path) if request.values_path else {}
    flat_values = flatten_values(values)
    unknown_values = set(flat_values) - set(available)
    unknown_overrides = set(request.overrides) - set(available)
    if unknown_values or unknown_overrides:
        unknown = sorted(unknown_values | unknown_overrides)
        raise ResolutionError(f"unknown runtime value(s): {', '.join(unknown)}")
    context = RuntimeValueResolver(selected).resolve(
        values={key: value for key, value in flat_values.items() if key in selected},
        overrides={key: value for key, value in request.overrides.items() if key in selected},
        interactive=request.interactive,
        input_fn=request.input_fn,
    )
    return materialize_as(template, prefix, context, target), context
