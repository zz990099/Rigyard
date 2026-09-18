"""Application boundary for inline runtime value discovery and resolution."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from ..builds.models import BuildSpec
from ..config.loader import load_config, load_values
from ..config.models import RigyardConfig
from ..containers.models import ContainerSpec
from ..errors import ResolutionError
from ..images.models import ImageSpec
from ..parameters.context import ResolvedContext
from ..parameters.prompt import Formatter
from ..parameters.resolver import (
    RuntimeValueResolver,
    collect_prompts,
    flatten_values,
    materialize_as,
)
from ..parameters.sources import DynamicSources
from ..parameters.templates import (
    StringTemplateRenderer,
    TemplateContext,
    validate_template_syntax,
)
from ..scenarios.models import (
    ScenarioComposeSpec,
    ScenarioInstanceSpec,
    ScenarioProfileSpec,
)
from .requests import ResolutionRequest

ModelT = TypeVar("ModelT", bound=BaseModel)


class ValidateConfigUseCase:
    def execute(self, config_path: str | Path) -> RigyardConfig:
        config = load_config(config_path)
        _validate_config_templates(config, config_path)
        return config


class InspectParametersUseCase:
    def execute(self, config_path: str | Path) -> dict[str, Any]:
        config = load_config(config_path)
        _validate_config_templates(config, config_path)
        prompts = collect_prompts(config)
        return {
            "version": config.version,
            "runtime_values": RuntimeValueResolver(prompts).inspect(),
        }


class ResolveParametersUseCase:
    def __init__(
        self,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.sources = dict(sources or {})
        self.formatter = formatter

    def execute(
        self, request: ResolutionRequest, *, allow_missing: bool = False
    ) -> ResolvedContext:
        config = load_config(request.config_path)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                os.environ,
                config_path=request.config_path,
                variables=config.variables,
            )
        )
        context = resolve_prompts(
            config,
            request,
            allow_missing=allow_missing,
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
        )
        if not allow_missing:
            for name, template in config.images.items():
                materialize_as(template, f"images.{name}", context, ImageSpec, renderer)
            for name, template in config.containers.items():
                materialize_as(template, f"containers.{name}", context, ContainerSpec, renderer)
            for name, template in config.builds.items():
                materialize_as(template, f"builds.{name}", context, BuildSpec, renderer)
            for scene_name, scenario in config.scenarios.items():
                if scenario.compose is not None:
                    materialize_as(
                        scenario.compose,
                        f"scenarios.{scene_name}.compose",
                        context,
                        ScenarioComposeSpec,
                        renderer,
                    )
                for instance_name, instance in scenario.instances.items():
                    materialize_as(
                        instance,
                        f"scenarios.{scene_name}.instances.{instance_name}",
                        context,
                        ScenarioInstanceSpec,
                        renderer,
                    )
                for profile_name, profile in scenario.profiles.items():
                    materialize_as(
                        profile,
                        f"scenarios.{scene_name}.profiles.{profile_name}",
                        context,
                        ScenarioProfileSpec,
                        renderer,
                    )
        return context


def _validate_config_templates(config: RigyardConfig, config_path: str | Path) -> None:
    base = TemplateContext.capture({}, config_path=config_path)
    previous: list[str] = []
    for name, value in config.variables.items():
        StringTemplateRenderer(base, variable_names=previous).validate(value, f"variables.{name}")
        previous.append(name)
    validate_template_syntax(
        config,
        renderer=StringTemplateRenderer(base, variable_names=config.variables),
    )


def resolve_prompts(
    template: BaseModel,
    request: ResolutionRequest,
    *,
    prefix: str = "",
    allow_missing: bool = False,
    renderer: StringTemplateRenderer | None = None,
    sources: DynamicSources | None = None,
    formatter: Formatter | None = None,
) -> ResolvedContext:
    prompts = collect_prompts(template, prefix)
    values = load_values(request.values_path) if request.values_path else {}
    return RuntimeValueResolver(
        prompts,
        render_default=default_display_renderer(renderer),
        sources=sources,
        formatter=formatter,
    ).resolve(
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
    renderer: StringTemplateRenderer | None = None,
    sources: DynamicSources | None = None,
    formatter: Formatter | None = None,
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
    context = RuntimeValueResolver(
        selected,
        render_default=default_display_renderer(renderer),
        sources=sources,
        formatter=formatter,
    ).resolve(
        values={key: value for key, value in flat_values.items() if key in selected},
        overrides={key: value for key, value in request.overrides.items() if key in selected},
        interactive=request.interactive,
        input_fn=request.input_fn,
    )
    return materialize_as(template, prefix, context, target, renderer), context


def resolve_selected_prompts(
    root: BaseModel,
    selected: dict[str, Any],
    request: ResolutionRequest,
    *,
    renderer: StringTemplateRenderer | None = None,
    sources: DynamicSources | None = None,
    formatter: Formatter | None = None,
) -> ResolvedContext:
    """Resolve an explicitly composed set of prompt paths from one config root."""

    available = collect_prompts(root)
    values = load_values(request.values_path) if request.values_path else {}
    flat_values = flatten_values(values)
    unknown = (set(flat_values) | set(request.overrides)) - set(available)
    if unknown:
        raise ResolutionError(f"unknown runtime value(s): {', '.join(sorted(unknown))}")
    return RuntimeValueResolver(
        selected,
        render_default=default_display_renderer(renderer),
        sources=sources,
        formatter=formatter,
    ).resolve(
        values={key: value for key, value in flat_values.items() if key in selected},
        overrides={key: value for key, value in request.overrides.items() if key in selected},
        interactive=request.interactive,
        input_fn=request.input_fn,
    )


def default_display_renderer(
    renderer: StringTemplateRenderer | None,
) -> Callable[[str, Any], str] | None:
    """Adapt a template renderer for rendering prompt defaults in hints."""
    if renderer is None:
        return None

    def render(path: str, value: Any) -> str:
        return str(renderer.render_value(value, path))

    return render
