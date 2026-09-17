"""Create backend-specific scenario plans from selected groups and profiles."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..errors import ScenarioPlanError, SourceLocation
from .models import (
    ComposeSupervisorPlan,
    ComposeSupervisorProfileSpec,
    ScenarioGroupPlan,
    ScenarioGroupSpec,
    ScenarioPlan,
    TmuxProfileSpec,
    TmuxScenarioPlan,
)


class ScenarioPlanner:
    def create_plan(
        self,
        scene_name: str,
        profile_name: str,
        groups: dict[str, ScenarioGroupSpec],
        profile: TmuxProfileSpec | ComposeSupervisorProfileSpec,
        config_path: str | Path,
        project_name: str,
    ) -> ScenarioPlan:
        enabled = tuple(
            ScenarioGroupPlan(
                name=name,
                container=group.container,
                service=group.service,
                script=group.script,
                interpreter=group.interpreter,
                user=group.user,
                workdir=group.workdir,
                environment=tuple(sorted(group.environment.items())),
                supervisor=group.supervisor,
            )
            for name, group in groups.items()
            if group.enabled
        )
        if not enabled:
            raise ScenarioPlanError(f"scenario {scene_name!r} has no enabled groups")
        for group in enabled:
            _validate_group_text(group)

        config_file = Path(config_path).resolve()
        if isinstance(profile, TmuxProfileSpec):
            compose_file = None
            compose_project = None
            if profile.compose_file is not None:
                compose_file = _resolve_path(config_file.parent, profile.compose_file)
                if not compose_file.is_file():
                    raise ScenarioPlanError(f"compose file is not a file: {compose_file}")
                compose_project = profile.project_name or _runtime_name(
                    config_file, project_name, scene_name
                )
                _validate_compose_name(compose_project, "Compose project")
                missing = [group.name for group in enabled if not group.service]
            else:
                if profile.project_name is not None:
                    raise ScenarioPlanError("tmux project_name requires compose_file")
                missing = [group.name for group in enabled if not group.container]
            if missing:
                raise ScenarioPlanError(
                    "tmux profile requires "
                    + ("service" if compose_file else "container")
                    + " for group(s): " + ", ".join(missing)
                )
            if compose_file is not None:
                for group in enabled:
                    _validate_compose_name(group.service or "", "Compose service")
            session = profile.session or _runtime_name(config_file, project_name, scene_name)
            _validate_tmux_name(session)
            return TmuxScenarioPlan(
                scene_name,
                profile_name,
                session,
                profile.attach,
                True,
                profile.stop_grace_seconds,
                enabled,
                compose_file,
                compose_project,
                profile.wait_timeout_seconds,
            )

        missing = [group.name for group in enabled if not group.service]
        if missing:
            raise ScenarioPlanError(
                "compose-supervisor profile requires service for group(s): " + ", ".join(missing)
            )
        for group in enabled:
            _validate_compose_name(group.service or "", f"service for group {group.name!r}")
        compose_file = _resolve_path(config_file.parent, profile.compose_file)
        if not compose_file.is_file():
            raise ScenarioPlanError(
                f"scenario {scene_name!r} compose file is not a file: {compose_file}",
                SourceLocation(config_file),
            )
        config_dir = _resolve_path(config_file.parent, profile.supervisor_config_dir)
        if config_dir.exists() and not config_dir.is_dir():
            raise ScenarioPlanError(
                f"supervisor config path is not a directory: {config_dir}",
                SourceLocation(config_file),
            )
        compose_project = profile.project_name or _runtime_name(
            config_file, project_name, scene_name
        )
        _validate_compose_name(compose_project, "Compose project")
        return ComposeSupervisorPlan(
            scene_name,
            profile_name,
            compose_file,
            compose_project,
            config_dir,
            enabled,
        )


def _resolve_path(project_dir: Path, configured: Path) -> Path:
    path = configured.expanduser()
    return (project_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _runtime_name(config_file: Path, project_name: str, scene_name: str) -> str:
    source = f"{config_file}:{project_name}:{scene_name}"
    digest = hashlib.sha256(source.encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9_-]+", "-", f"{project_name}-{scene_name}".lower()).strip("-")
    return f"tc-{slug[:40]}-{digest}" if slug else f"tc-scene-{digest}"


def _validate_tmux_name(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", value):
        raise ScenarioPlanError(f"invalid tmux session name {value!r}")


def _validate_compose_name(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", value):
        raise ScenarioPlanError(f"invalid {label} name {value!r}")


def _validate_group_text(group: ScenarioGroupPlan) -> None:
    values = [group.script, *group.interpreter, group.user, group.workdir]
    values.extend(value for _, value in group.environment)
    if any(value is not None and any(char in value for char in "\x00\r\n") for value in values):
        raise ScenarioPlanError(f"scenario group {group.name!r} contains control characters")
