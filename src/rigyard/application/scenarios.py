"""Application boundary for selecting and planning named scenario profiles."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import datetime

from ..config.loader import load_config
from ..errors import SchemaValidationError
from ..parameters.models import PromptValue
from ..parameters.prompt import Formatter
from ..parameters.resolver import collect_prompts, materialize, materialize_as
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from ..scenarios.models import (
    ScenarioComposeSpec,
    ScenarioGroupSpec,
    ScenarioInstanceSpec,
    ScenarioInstanceTemplate,
    ScenarioPlan,
    ScenarioProfileSpec,
    ScenarioStartupSpec,
    ScenarioTemplate,
)
from ..scenarios.planner import ScenarioPlanner
from .definitions import find_definition
from .parameters import resolve_selected_prompts
from .requests import ResolutionRequest


class PlanScenarioUseCase:
    def __init__(
        self,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        scene_name: str,
        profile_name: str | None,
        request: ResolutionRequest,
        *,
        resolve_group_runtime: bool = True,
        instances: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ScenarioPlan:
        config = load_config(request.config_path)
        if scene_name not in config.scenarios:
            available = ", ".join(sorted(config.scenarios)) or "none"
            raise SchemaValidationError(
                f"unknown scenario {scene_name!r}; configured scenarios: {available}"
            )
        match = find_definition(
            config,
            "scenarios",
            scene_name,
            request.source_path,
            request.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.scenarios)) or "none"
            raise SchemaValidationError(
                f"unknown scenario {scene_name!r}; configured scenarios: {available}"
            )
        scenario = match.value
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                dict(os.environ if environment is None else environment),
                now=now,
                config_path=request.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        compose_managed = scenario.compose is not None
        profile_name = _select_profile_name(scene_name, scenario, profile_name)
        if profile_name not in scenario.profiles:
            available = ", ".join(sorted(scenario.profiles)) or "none"
            raise SchemaValidationError(
                f"unknown profile {profile_name!r} for scenario {scene_name!r}; "
                f"configured profiles: {available}"
            )

        instances_prefix = f"scenarios.{scene_name}.instances"
        profile_prefix = f"scenarios.{scene_name}.profiles.{profile_name}"
        compose_prefix = f"scenarios.{scene_name}.compose"
        startup_prefix = f"scenarios.{scene_name}.startup"
        profile_template = scenario.profiles[profile_name]
        profile_prompts = collect_prompts(profile_template, profile_prefix)
        compose_prompts = (
            collect_prompts(scenario.compose, compose_prefix)
            if scenario.compose is not None
            else {}
        )
        startup_prompts = (
            collect_prompts(scenario.startup, startup_prefix) if resolve_group_runtime else {}
        )
        instance_prompts = {
            path: value
            for name, instance in scenario.instances.items()
            for path, value in collect_prompts(
                instance.enabled, f"{instances_prefix}.{name}.enabled"
            ).items()
        }
        group_prompts = {
            path: value
            for name, instance in scenario.instances.items()
            for group_name, group in instance.groups.items()
            for path, value in collect_prompts(
                group.enabled, f"{instances_prefix}.{name}.groups.{group_name}.enabled"
            ).items()
        }
        selection_context = resolve_selected_prompts(
            config,
            {**profile_prompts, **compose_prompts, **instance_prompts, **group_prompts},
            request,
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
        )
        selected_names = _select_instances(
            scene_name,
            scenario.instances,
            instances,
            selection_context,
            instances_prefix,
        )
        enabled_groups = {
            name: {
                group_name
                for group_name, group in scenario.instances[name].groups.items()
                if _enabled(
                    group.enabled,
                    selection_context,
                    f"{instances_prefix}.{name}.groups.{group_name}.enabled",
                )
            }
            for name in scenario.instances
        }

        selected = {
            **profile_prompts,
            **compose_prompts,
            **startup_prompts,
            **instance_prompts,
            **group_prompts,
        }
        for name in selected_names:
            instance = scenario.instances[name]
            prefix = f"{instances_prefix}.{name}"
            if compose_managed:
                selected.update(collect_prompts(instance.service, f"{prefix}.service"))
            else:
                selected.update(collect_prompts(instance.container, f"{prefix}.container"))
            if resolve_group_runtime:
                selected.update(collect_prompts(instance.enabled, f"{prefix}.enabled"))
                selected.update(collect_prompts(instance.startup, f"{prefix}.startup"))
                for group_name in enabled_groups[name]:
                    selected.update(
                        collect_prompts(
                            instance.groups[group_name], f"{prefix}.groups.{group_name}"
                        )
                    )
        context = resolve_selected_prompts(
            config,
            selected,
            ResolutionRequest(
                request.config_path,
                request.values_path,
                {**request.overrides, **selection_context.as_dict()},
                request.interactive,
                request.input_fn,
            ),
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
        )

        planned: dict[str, ScenarioInstanceSpec] = {}
        for name in selected_names:
            template = scenario.instances[name]
            prefix = f"{instances_prefix}.{name}"
            groups: dict[str, ScenarioGroupSpec] = {}
            for group_name, group in template.groups.items():
                if group_name not in enabled_groups[name]:
                    continue
                group_prefix = f"{prefix}.groups.{group_name}"
                if resolve_group_runtime:
                    groups[group_name] = materialize_as(
                        group, group_prefix, context, ScenarioGroupSpec, renderer
                    )
                else:
                    groups[group_name] = ScenarioGroupSpec(script=":")
            if not groups:
                raise SchemaValidationError(f"scenario instance {name!r} has no enabled groups")
            if compose_managed:
                if template.service is None:
                    raise SchemaValidationError(f"scenario instance {name!r} requires service")
                planned[name] = ScenarioInstanceSpec(
                    service=materialize(template.service, f"{prefix}.service", context, renderer),
                    startup=(
                        materialize_as(
                            template.startup,
                            f"{prefix}.startup",
                            context,
                            ScenarioStartupSpec,
                            renderer,
                        )
                        if resolve_group_runtime
                        else ScenarioStartupSpec()
                    ),
                    groups=groups,
                )
            else:
                if template.container is None:
                    raise SchemaValidationError(f"scenario instance {name!r} requires container")
                planned[name] = ScenarioInstanceSpec(
                    container=materialize(
                        template.container, f"{prefix}.container", context, renderer
                    ),
                    startup=(
                        materialize_as(
                            template.startup,
                            f"{prefix}.startup",
                            context,
                            ScenarioStartupSpec,
                            renderer,
                        )
                        if resolve_group_runtime
                        else ScenarioStartupSpec()
                    ),
                    groups=groups,
                )

        profile = materialize_as(
            profile_template,
            profile_prefix,
            context,
            ScenarioProfileSpec,
            renderer,
        )
        compose = (
            materialize_as(
                scenario.compose,
                compose_prefix,
                context,
                ScenarioComposeSpec,
                renderer,
            )
            if scenario.compose is not None
            else None
        )
        startup = (
            materialize_as(
                scenario.startup,
                startup_prefix,
                context,
                ScenarioStartupSpec,
                renderer,
            )
            if resolve_group_runtime
            else ScenarioStartupSpec()
        )
        return ScenarioPlanner().create_plan(
            scene_name,
            profile_name,
            planned,
            profile,
            compose,
            startup,
            request.config_path,
            config.metadata.name,
            partial=bool(instances),
        )


def _select_instances(
    scene_name: str,
    templates: Mapping[str, ScenarioInstanceTemplate],
    requested: Sequence[str] | None,
    selection_context: Mapping[str, object],
    instances_prefix: str,
) -> list[str]:
    names = list(templates)
    if requested:
        unknown = [name for name in requested if name not in templates]
        if unknown:
            available = ", ".join(sorted(templates)) or "none"
            raise SchemaValidationError(
                f"unknown instance(s) for scenario {scene_name!r}: {', '.join(unknown)}; "
                f"configured instances: {available}"
            )
    enabled = {
        name: _enabled(
            templates[name].enabled,
            selection_context,
            f"{instances_prefix}.{name}.enabled",
        )
        for name in names
    }
    if requested:
        disabled = [name for name in requested if not enabled[name]]
        if disabled:
            raise SchemaValidationError(f"scenario instance(s) are disabled: {', '.join(disabled)}")
        wanted = set(requested)
        return [name for name in names if name in wanted]
    return [name for name in names if enabled[name]]


def _enabled(value: object, context: Mapping[str, object], path: str) -> bool:
    resolved = context[path] if isinstance(value, PromptValue) else value
    return bool(resolved)


def _select_profile_name(
    scene_name: str,
    scenario: ScenarioTemplate,
    profile_name: str | None,
) -> str:
    """Use the only configured profile when the caller did not name one."""

    if profile_name is not None:
        return profile_name
    profiles = list(scenario.profiles)
    if len(profiles) == 1:
        return profiles[0]
    available = ", ".join(sorted(profiles)) or "none"
    raise SchemaValidationError(
        f"scenario {scene_name!r} needs a profile; configured profiles: {available}"
    )
