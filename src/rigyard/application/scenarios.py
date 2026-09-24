"""Application boundary for selecting and planning named scenario profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from ..errors import ResolutionError, SchemaValidationError
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
    ScenarioProfileTemplate,
    ScenarioStartupSpec,
    ScenarioTemplate,
)
from ..scenarios.planner import ScenarioPlanner
from .definitions import find_definition
from .parameters import resolve_selected_prompts
from .project import ProjectContext, project_context
from .requests import ResolutionRequest

ScenarioOperation = Literal["start", "stop", "down", "status", "attach", "logs"]


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
        operation: ScenarioOperation = "start",
        instances: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ScenarioPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
        )
        config = project.config
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
            project.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.scenarios)) or "none"
            raise SchemaValidationError(
                f"unknown scenario {scene_name!r}; configured scenarios: {available}"
            )
        scenario = match.value
        profile_name = _select_profile_name(scene_name, scenario, profile_name)
        if profile_name not in scenario.profiles:
            available = ", ".join(sorted(scenario.profiles)) or "none"
            raise SchemaValidationError(
                f"unknown profile {profile_name!r} for scenario {scene_name!r}; "
                f"configured profiles: {available}"
            )
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                project.environment,
                now=project.timestamp,
                config_path=project.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        if operation != "start":
            return self._plan_control(
                scene_name,
                profile_name,
                scenario,
                operation,
                instances,
                request,
                project,
                renderer,
                match.source_path,
            )
        compose_managed = scenario.compose is not None

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
        startup_prompts = collect_prompts(scenario.startup, startup_prefix)
        candidate_names = _select_control_instances(scene_name, scenario.instances, instances)
        instance_prompts = {
            path: value
            for name in candidate_names
            for path, value in collect_prompts(
                scenario.instances[name].enabled, f"{instances_prefix}.{name}.enabled"
            ).items()
        }
        instance_context = resolve_selected_prompts(
            config,
            instance_prompts,
            request,
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
            environment=project.environment,
        )
        selected_names = _select_instances(
            scene_name,
            {name: scenario.instances[name] for name in candidate_names},
            instances,
            instance_context,
            instances_prefix,
        )
        group_prompts = {
            path: value
            for name in selected_names
            for group_name, group in scenario.instances[name].groups.items()
            for path, value in collect_prompts(
                group.enabled, f"{instances_prefix}.{name}.groups.{group_name}.enabled"
            ).items()
        }
        group_context = resolve_selected_prompts(
            config,
            group_prompts,
            request,
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
            environment=project.environment,
        )
        enabled_groups = {
            name: {
                group_name
                for group_name, group in scenario.instances[name].groups.items()
                if _enabled(
                    group.enabled,
                    group_context,
                    f"{instances_prefix}.{name}.groups.{group_name}.enabled",
                )
            }
            for name in selected_names
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
            selected.update(collect_prompts(instance.enabled, f"{prefix}.enabled"))
            selected.update(collect_prompts(instance.startup, f"{prefix}.startup"))
            for group_name in enabled_groups[name]:
                selected.update(
                    collect_prompts(instance.groups[group_name], f"{prefix}.groups.{group_name}")
                )
        context = resolve_selected_prompts(
            config,
            selected,
            ResolutionRequest(
                request.config_path,
                request.values_path,
                {**request.overrides, **instance_context.as_dict(), **group_context.as_dict()},
                request.interactive,
                request.input_fn,
                project=project,
            ),
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
            environment=project.environment,
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
                groups[group_name] = materialize_as(
                    group, group_prefix, context, ScenarioGroupSpec, renderer
                )
            if not groups:
                raise SchemaValidationError(f"scenario instance {name!r} has no enabled groups")
            if compose_managed:
                if template.service is None:
                    raise SchemaValidationError(f"scenario instance {name!r} requires service")
                planned[name] = ScenarioInstanceSpec(
                    service=materialize(template.service, f"{prefix}.service", context, renderer),
                    startup=materialize_as(
                        template.startup,
                        f"{prefix}.startup",
                        context,
                        ScenarioStartupSpec,
                        renderer,
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
                    startup=materialize_as(
                        template.startup,
                        f"{prefix}.startup",
                        context,
                        ScenarioStartupSpec,
                        renderer,
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
        startup = materialize_as(
            scenario.startup,
            startup_prefix,
            context,
            ScenarioStartupSpec,
            renderer,
        )
        return ScenarioPlanner().create_plan(
            scene_name,
            profile_name,
            planned,
            profile,
            compose,
            startup,
            project.config_path,
            config.metadata.name,
            partial=bool(instances),
            source_path=match.source_path,
        )

    def _plan_control(
        self,
        scene_name: str,
        profile_name: str,
        scenario: ScenarioTemplate,
        operation: ScenarioOperation,
        instances: Sequence[str] | None,
        request: ResolutionRequest,
        project: ProjectContext,
        renderer: StringTemplateRenderer,
        source_path: Path,
    ) -> ScenarioPlan:
        profile_prefix = f"scenarios.{scene_name}.profiles.{profile_name}"
        compose_prefix = f"scenarios.{scene_name}.compose"
        profile_template = scenario.profiles[profile_name]
        needs_stop_grace = operation in {"stop", "down"}
        control_profile = ScenarioProfileTemplate(
            session=profile_template.session,
            attach=False,
            stop_grace_seconds=(profile_template.stop_grace_seconds if needs_stop_grace else 0),
            restart_container="never",
            mouse=False,
            keep_alive=False,
        )
        selected = collect_prompts(control_profile, profile_prefix)
        if operation == "down" and scenario.compose is not None:
            selected.update(collect_prompts(scenario.compose, compose_prefix))
        context = resolve_selected_prompts(
            project.config,
            selected,
            ResolutionRequest(
                request.config_path,
                request.values_path,
                request.overrides,
                request.interactive,
                request.input_fn,
                project=project,
            ),
            renderer=renderer,
            sources=self.sources,
            formatter=self.formatter,
            environment=project.environment,
        )
        profile = materialize_as(
            control_profile,
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
            if operation == "down" and scenario.compose is not None
            else None
        )
        selected_names = _select_control_instances(scene_name, scenario.instances, instances)
        groups = (
            {name: tuple(scenario.instances[name].groups) for name in selected_names}
            if operation in {"attach", "logs"}
            else {}
        )
        return ScenarioPlanner().create_control_plan(
            scene_name,
            profile_name,
            selected_names,
            groups,
            profile,
            compose,
            project.config_path,
            project.config.metadata.name,
            partial=bool(instances),
            source_path=source_path,
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


def _select_control_instances(
    scene_name: str,
    templates: Mapping[str, ScenarioInstanceTemplate],
    requested: Sequence[str] | None,
) -> list[str]:
    names = list(templates)
    if not requested:
        return names
    unknown = [name for name in requested if name not in templates]
    if unknown:
        available = ", ".join(sorted(templates)) or "none"
        raise SchemaValidationError(
            f"unknown instance(s) for scenario {scene_name!r}: {', '.join(unknown)}; "
            f"configured instances: {available}"
        )
    wanted = set(requested)
    return [name for name in names if name in wanted]


def _enabled(value: object, context: Mapping[str, object], path: str) -> bool:
    resolved = context[path] if isinstance(value, PromptValue) else value
    try:
        return TypeAdapter(bool).validate_python(resolved)
    except ValidationError as exc:
        raise ResolutionError(f"invalid enabled value for {path}: expected a boolean") from exc


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
