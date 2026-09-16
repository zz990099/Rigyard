"""Application boundary for selecting and planning named scenario profiles."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..config.loader import load_config
from ..errors import SchemaValidationError
from ..parameters.models import PromptValue
from ..parameters.resolver import collect_prompts, materialize_as
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from ..scenarios.models import (
    ComposeSupervisorProfileSpec,
    ComposeSupervisorProfileTemplate,
    ScenarioGroupSpec,
    ScenarioPlan,
    TmuxProfileSpec,
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
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ScenarioPlan:
        config = load_config(request.config_path)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                dict(os.environ if environment is None else environment),
                now=now,
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

        group_prefix = f"scenarios.{scene_name}.groups"
        profile_prefix = f"scenarios.{scene_name}.profiles.{profile_name}"
        profile_template = scenario.profiles[profile_name]
        profile_prompts = collect_prompts(profile_template, profile_prefix)
        enabled_prompts = {
            path: value
            for name, group in scenario.groups.items()
            for path, value in collect_prompts(
                group.enabled,
                f"{group_prefix}.{name}.enabled",
            ).items()
        }
        selection_context = resolve_selected_prompts(
            config,
            {**profile_prompts, **enabled_prompts},
            request,
        )
        enabled_names = {
            name
            for name, group in scenario.groups.items()
            if (
                selection_context[f"{group_prefix}.{name}.enabled"]
                if isinstance(group.enabled, PromptValue)
                else group.enabled
            )
        }
        selected = dict(profile_prompts)
        for name, group in scenario.groups.items():
            prefix = f"{group_prefix}.{name}"
            if name in enabled_names and resolve_group_runtime:
                selected.update(collect_prompts(group, prefix))
            elif name in enabled_names and isinstance(
                profile_template, ComposeSupervisorProfileTemplate
            ):
                selected.update(collect_prompts(group.service, f"{prefix}.service"))
            else:
                selected.update(collect_prompts(group.enabled, f"{prefix}.enabled"))
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

        if resolve_group_runtime:
            groups = {
                name: materialize_as(
                    group,
                    f"{group_prefix}.{name}",
                    context,
                    ScenarioGroupSpec,
                    renderer,
                )
                for name, group in scenario.groups.items()
                if name in enabled_names
            }
        else:
            compose_profile = isinstance(profile_template, ComposeSupervisorProfileTemplate)
            groups = {
                name: ScenarioGroupSpec(
                    container="management" if not compose_profile else None,
                    service=renderer.render_value(
                        (
                            context[f"{group_prefix}.{name}.service"]
                            if isinstance(group.service, PromptValue)
                            else group.service
                        ),
                        f"{group_prefix}.{name}.service",
                    ),
                    script=":",
                )
                for name, group in scenario.groups.items()
                if name in enabled_names
            }
        profile_type = (
            ComposeSupervisorProfileSpec
            if isinstance(profile_template, ComposeSupervisorProfileTemplate)
            else TmuxProfileSpec
        )
        profile = materialize_as(
            profile_template,
            profile_prefix,
            context,
            profile_type,
            renderer,
        )
        return ScenarioPlanner().create_plan(
            scene_name,
            profile_name,
            groups,
            profile,
            request.config_path,
            config.metadata.name,
        )
