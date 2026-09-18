"""Application boundary for selecting and planning named scenario profiles."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import datetime

from ..config.loader import load_config
from ..errors import SchemaValidationError
from ..parameters.models import PromptValue
from ..parameters.resolver import collect_prompts, materialize, materialize_as
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from ..scenarios.models import (
    ScenarioComposeSpec,
    ScenarioGroupSpec,
    ScenarioInstanceSpec,
    ScenarioInstanceTemplate,
    ScenarioPlan,
    ScenarioProfileSpec,
)
from ..scenarios.planner import ScenarioPlanner
from .parameters import resolve_selected_prompts
from .requests import ResolutionRequest


class PlanScenarioUseCase:
    def plan(
        self,
        scene_name: str,
        profile_name: str,
        request: ResolutionRequest,
        *,
        resolve_group_runtime: bool = True,
        instances: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ScenarioPlan:
        config = load_config(request.config_path)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                dict(os.environ if environment is None else environment),
                now=now,
                config_path=request.config_path,
                variables=config.variables,
            )
        )
        if scene_name not in config.scenarios:
            available = ", ".join(sorted(config.scenarios)) or "none"
            raise SchemaValidationError(
                f"unknown scenario {scene_name!r}; configured scenarios: {available}"
            )
        scenario = config.scenarios[scene_name]
        if profile_name not in scenario.profiles:
            available = ", ".join(sorted(scenario.profiles)) or "none"
            raise SchemaValidationError(
                f"unknown profile {profile_name!r} for scenario {scene_name!r}; "
                f"configured profiles: {available}"
            )

        instances_prefix = f"scenarios.{scene_name}.instances"
        profile_prefix = f"scenarios.{scene_name}.profiles.{profile_name}"
        compose_prefix = f"scenarios.{scene_name}.compose"
        profile_template = scenario.profiles[profile_name]
        profile_prompts = collect_prompts(profile_template, profile_prefix)
        compose_prompts = (
            collect_prompts(scenario.compose, compose_prefix)
            if scenario.compose is not None
            else {}
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
            **instance_prompts,
            **group_prompts,
        }
        for name in selected_names:
            instance = scenario.instances[name]
            prefix = f"{instances_prefix}.{name}"
            selected.update(collect_prompts(instance.container, f"{prefix}.container"))
            if resolve_group_runtime:
                selected.update(collect_prompts(instance.enabled, f"{prefix}.enabled"))
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
            planned[name] = ScenarioInstanceSpec(
                container=materialize(template.container, f"{prefix}.container", context, renderer),
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
        return ScenarioPlanner().create_plan(
            scene_name,
            profile_name,
            planned,
            profile,
            compose,
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
