"""Create backend-specific scenario plans from selected instances and profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..errors import ScenarioPlanError
from .identity import ScenarioIdentity
from .models import (
    ScenarioComposePlan,
    ScenarioComposeSpec,
    ScenarioGroupPlan,
    ScenarioInstancePlan,
    ScenarioInstanceSpec,
    ScenarioPlan,
    ScenarioProfileSpec,
    ScenarioStartupPlan,
    ScenarioStartupSpec,
)

CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
TMUX_WINDOW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")


class ScenarioPlanner:
    def create_plan(
        self,
        scene_name: str,
        profile_name: str,
        instances: dict[str, ScenarioInstanceSpec],
        profile: ScenarioProfileSpec,
        compose: ScenarioComposeSpec | None,
        startup: ScenarioStartupSpec,
        config_path: str | Path,
        project_name: str,
        *,
        partial: bool = False,
        source_path: Path | None = None,
    ) -> ScenarioPlan:
        planned = tuple(
            _instance_plan(name, instance)
            for name, instance in instances.items()
            if instance.enabled
        )
        if not planned:
            raise ScenarioPlanError(f"scenario {scene_name!r} has no enabled instances")
        for instance in planned:
            for group in instance.groups:
                _validate_group_text(group)

        config_file = Path(config_path).resolve()
        identity = ScenarioIdentity(
            config_file, (source_path or config_file).resolve(), scene_name, profile_name
        )
        for instance in planned:
            _validate_window_name(instance.name)
            if compose is None:
                if instance.container is None:
                    raise ScenarioPlanError(
                        f"scenario instance {instance.name!r} requires a container"
                    )
                _validate_container_name(instance.container)
            else:
                if instance.service is None:
                    raise ScenarioPlanError(
                        f"scenario instance {instance.name!r} requires a Compose service"
                    )
                if instance.container is not None:
                    raise ScenarioPlanError(
                        f"scenario instance {instance.name!r} must use service, not container, "
                        "for Compose-managed scenarios"
                    )
                _validate_compose_service_name(instance.service)
        compose_plan = _compose_plan(
            compose,
            config_file,
            project_name,
            identity,
        )
        session = profile.session or identity.runtime_name(project_name)
        _validate_tmux_name(session)
        return ScenarioPlan(
            scene_name=scene_name,
            profile_name=profile_name,
            session=session,
            attach=profile.attach,
            stop_grace_seconds=profile.stop_grace_seconds,
            instances=planned,
            compose=compose_plan,
            restart_container=profile.restart_container,
            mouse=profile.mouse,
            keep_alive=profile.keep_alive,
            partial=partial,
            identity=identity,
            startup=_startup_plan(startup),
        )

    def create_control_plan(
        self,
        scene_name: str,
        profile_name: str,
        instance_names: Sequence[str],
        groups: Mapping[str, Sequence[str]],
        profile: ScenarioProfileSpec,
        compose: ScenarioComposeSpec | None,
        config_path: str | Path,
        project_name: str,
        *,
        partial: bool = False,
        source_path: Path | None = None,
    ) -> ScenarioPlan:
        config_file = Path(config_path).resolve()
        identity = ScenarioIdentity(
            config_file, (source_path or config_file).resolve(), scene_name, profile_name
        )
        planned = tuple(
            ScenarioInstancePlan(
                name=name,
                container=None,
                groups=tuple(
                    ScenarioGroupPlan(
                        name=group_name,
                        script=None,
                        interpreter=(),
                        user=None,
                        workdir=None,
                        environment=(),
                    )
                    for group_name in groups.get(name, ())
                ),
            )
            for name in instance_names
        )
        if not planned:
            raise ScenarioPlanError(f"scenario {scene_name!r} has no configured instances")
        for instance in planned:
            _validate_window_name(instance.name)
        compose_plan = _compose_plan(
            compose,
            config_file,
            project_name,
            identity,
        )
        session = profile.session or identity.runtime_name(project_name)
        _validate_tmux_name(session)
        return ScenarioPlan(
            scene_name=scene_name,
            profile_name=profile_name,
            session=session,
            attach=False,
            stop_grace_seconds=profile.stop_grace_seconds,
            instances=planned,
            compose=compose_plan,
            restart_container="never",
            mouse=False,
            keep_alive=False,
            partial=partial,
            identity=identity,
        )


def _instance_plan(name: str, instance: ScenarioInstanceSpec) -> ScenarioInstancePlan:
    groups = tuple(
        ScenarioGroupPlan(
            name=group_name,
            script=group.script,
            command=group.command,
            setup=group.setup,
            interpreter=group.interpreter,
            user=group.user,
            workdir=group.workdir,
            environment=tuple(sorted(group.environment.items())),
        )
        for group_name, group in instance.groups.items()
        if group.enabled
    )
    if not groups:
        raise ScenarioPlanError(f"scenario instance {name!r} has no enabled groups")
    return ScenarioInstancePlan(
        name,
        instance.container,
        groups,
        service=instance.service,
        startup=_startup_plan(instance.startup),
    )


def _startup_plan(startup: ScenarioStartupSpec) -> ScenarioStartupPlan:
    return ScenarioStartupPlan(startup.mode, startup.interval_seconds)


def _compose_plan(
    compose: ScenarioComposeSpec | None,
    config_file: Path,
    project_name: str,
    identity: ScenarioIdentity,
) -> ScenarioComposePlan | None:
    if compose is None:
        return None
    compose_file = _resolve_path(config_file.parent, compose.file)
    if not compose_file.is_file():
        raise ScenarioPlanError(f"Compose file is not a file: {compose_file}")
    compose_project = compose.project_name or identity.runtime_name(project_name)
    _validate_compose_project(compose_project)
    plan = ScenarioComposePlan(
        compose_file,
        compose_project,
        compose.wait_timeout_seconds,
        tuple(sorted(compose.environment.items())),
    )
    _validate_compose_environment(plan.environment)
    return plan


def _resolve_path(project_dir: Path, configured: Path) -> Path:
    path = configured.expanduser()
    return (project_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _validate_tmux_name(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", value):
        raise ScenarioPlanError(f"invalid tmux session name {value!r}")


def _validate_window_name(value: str) -> None:
    # Window names double as tmux targets, so '.' and ':' would make them ambiguous.
    if not TMUX_WINDOW_NAME.fullmatch(value):
        raise ScenarioPlanError(
            f"invalid tmux window name {value!r}; use letters, digits, '_' or '-'"
        )


def _validate_container_name(value: str) -> None:
    if not CONTAINER_NAME.fullmatch(value):
        raise ScenarioPlanError(f"invalid container name {value!r}")


def _validate_compose_service_name(value: str) -> None:
    if not CONTAINER_NAME.fullmatch(value):
        raise ScenarioPlanError(f"invalid Compose service name {value!r}")


def _validate_compose_project(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", value):
        raise ScenarioPlanError(f"invalid Compose project name {value!r}")


def _validate_compose_environment(values: tuple[tuple[str, str], ...]) -> None:
    invalid = sorted(
        name for name, _ in values if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
    )
    if invalid:
        raise ScenarioPlanError(
            "invalid Compose environment variable name(s): " + ", ".join(invalid)
        )
    if any("\x00" in value for _, value in values):
        raise ScenarioPlanError("Compose environment values must not contain NUL bytes")


def _validate_group_text(group: ScenarioGroupPlan) -> None:
    values: list[str | None] = [*group.interpreter, group.user, group.workdir, group.script]
    values.extend(group.command or ())
    values.extend(group.setup)
    values.extend(value for _, value in group.environment)
    if any(value is not None and any(char in value for char in "\x00\r\n") for value in values):
        raise ScenarioPlanError(f"scenario group {group.name!r} contains control characters")
