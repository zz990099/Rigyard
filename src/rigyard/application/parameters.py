"""Application boundary for inline runtime value discovery and resolution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    SourceAwareStringTemplateRenderer,
    StringTemplateRenderer,
    TemplateContext,
    validate_template_syntax,
)
from ..scenarios.models import (
    ScenarioComposeSpec,
    ScenarioInstanceSpec,
    ScenarioProfileSpec,
)
from ..tasks.models import TaskSpec
from ..tests.models import TestSpec
from .definitions import definition_source_paths
from .project import project_context
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
        prompts = _collect_config_prompts(config)
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
        project = project_context(request.config_path, request.project)
        config = project.config
        template_context = TemplateContext.capture(
            project.environment,
            now=project.timestamp,
            config_path=project.config_path,
            variables=config.variables,
        )
        renderer = SourceAwareStringTemplateRenderer(
            template_context,
            definition_source_paths(config),
        )
        context = resolve_prompts(
            config,
            request,
            allow_missing=allow_missing,
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
            environment=project.environment,
        )
        if not allow_missing:
            for name, image_template in config.images.items():
                materialize_as(image_template, f"images.{name}", context, ImageSpec, renderer)
            for name, container_template in config.containers.items():
                materialize_as(
                    container_template, f"containers.{name}", context, ContainerSpec, renderer
                )
            for name, build_template in config.builds.items():
                materialize_as(build_template, f"builds.{name}", context, BuildSpec, renderer)
            for name, test_template in config.tests.items():
                materialize_as(test_template, f"tests.{name}", context, TestSpec, renderer)
            for name, task_template in config.tasks.items():
                materialize_as(task_template, f"tasks.{name}", context, TaskSpec, renderer)
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
    environment: Mapping[str, str] | None = None,
) -> ResolvedContext:
    prompts = (
        _collect_config_prompts(template)
        if isinstance(template, RigyardConfig) and not prefix
        else collect_prompts(template, prefix)
    )
    values = load_values(request.values_path) if request.values_path else {}
    return RuntimeValueResolver(
        prompts,
        render_default=default_display_renderer(renderer),
        sources=sources,
        formatter=formatter,
    ).resolve(
        values=values,
        environ=environment if environment is not None else _request_environment(request),
        overrides=request.overrides,
        interactive=request.interactive,
        input_fn=request.input_fn,
        allow_missing=allow_missing,
    )


def _collect_config_prompts(config: RigyardConfig) -> dict[str, Any]:
    """Collect public resource prompts without internal source provenance copies."""

    prompts: dict[str, Any] = {}
    for kind in ("images", "containers", "builds", "tests", "tasks", "scenarios"):
        prompts.update(collect_prompts(getattr(config, kind), kind))
    return prompts


def resolve_template(
    root: BaseModel,
    template: BaseModel,
    request: ResolutionRequest,
    prefix: str,
    target: type[ModelT],
    renderer: StringTemplateRenderer | None = None,
    sources: DynamicSources | None = None,
    formatter: Formatter | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[ModelT, ResolvedContext]:
    selected = collect_prompts(template, prefix)
    available = (
        _collect_config_prompts(root) if isinstance(root, RigyardConfig) else collect_prompts(root)
    )
    available.update(selected)
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
        environ=environment if environment is not None else _request_environment(request),
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
    environment: Mapping[str, str] | None = None,
) -> ResolvedContext:
    """Resolve an explicitly composed set of prompt paths from one config root."""

    available = (
        _collect_config_prompts(root) if isinstance(root, RigyardConfig) else collect_prompts(root)
    )
    available.update(selected)
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
        environ=environment if environment is not None else _request_environment(request),
        overrides={key: value for key, value in request.overrides.items() if key in selected},
        interactive=request.interactive,
        input_fn=request.input_fn,
    )


def _request_environment(request: ResolutionRequest) -> Mapping[str, str] | None:
    return request.project.environment if request.project is not None else None


def default_display_renderer(
    renderer: StringTemplateRenderer | None,
) -> Callable[[str, Any], str] | None:
    """Adapt a template renderer for rendering prompt defaults in hints."""
    if renderer is None:
        return None

    def render(path: str, value: Any) -> str:
        return str(renderer.render_value(value, path))

    return render
