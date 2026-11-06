"""Resolve boot registration without starting containers or copying scenario YAML."""

from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..autostart.systemd import MARKER, SystemdManager, command_line, quote, scalar
from ..errors import ScenarioPlanError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..scenarios.identity import ScenarioIdentity
from ..scenarios.models import ScenarioPlan
from ..scenarios.records import FileRunStore
from .definitions import find_definition
from .project import project_context
from .requests import ResolutionRequest
from .scenarios import PlanScenarioUseCase, _select_profile_name


@dataclass(frozen=True)
class AutostartPlan:
    unit: str
    content: str
    scenario: ScenarioPlan


def unit_name(identity: ScenarioIdentity) -> str:
    return f"rigyard-autostart-{identity.key}.service"


def selected_unit(scene: str, profile: str | None, request: ResolutionRequest) -> str:
    # Control remains possible after source/config deletion when there is a run record.
    record = FileRunStore(request.config_path).find(scene, profile, request.source_path)
    if record is not None and record.target.owner_unit:
        return record.target.owner_unit
    project = project_context(
        request.config_path, request.project, workspace_root=request.workspace_root
    )
    match = find_definition(
        project.config, "scenarios", scene, request.source_path, project.config_path
    )
    if match is None:
        raise ScenarioPlanError(f"unknown scenario {scene!r}")
    from ..scenarios.models import ScenarioTemplate

    assert isinstance(match.value, ScenarioTemplate)
    name = _select_profile_name(scene, match.value, profile)
    if name not in match.value.profiles:
        raise ScenarioPlanError(f"unknown profile {name!r}")
    return unit_name(
        ScenarioIdentity(project.config_path.resolve(), match.source_path, scene, name)
    )


class PlanAutostartUseCase:
    def __init__(
        self, sources: DynamicSources | None = None, formatter: Formatter | None = None
    ) -> None:
        self.planner = PlanScenarioUseCase(sources=sources, formatter=formatter)

    def plan(
        self,
        scene: str,
        profile: str | None,
        request: ResolutionRequest,
        *,
        isolated_socket: bool = False,
    ) -> AutostartPlan:
        project = project_context(
            request.config_path, request.project, workspace_root=request.workspace_root
        )
        answers: dict[str, Any] = {}
        plan = self.planner.plan(scene, profile, replace(request, project=project), answers=answers)
        assert plan.identity is not None
        unit = unit_name(plan.identity)
        # Capture only connection/runtime essentials and referenced template variables.
        match = find_definition(
            project.config, "scenarios", scene, request.source_path, project.config_path
        )
        assert match is not None
        from ..scenarios.models import ScenarioTemplate

        assert isinstance(match.value, ScenarioTemplate)
        selected = {
            "variables": dict(project.config.variables),
            "compose": match.value.compose.model_dump(mode="json") if match.value.compose else None,
            "profile": match.value.profiles[plan.profile_name].model_dump(mode="json"),
            "instances": {
                i.name: match.value.instances[i.name].model_dump(mode="json")
                for i in plan.instances
            },
            "answers": answers,
        }
        referenced = set(
            re.findall(r"\$\{env:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", json.dumps(selected))
        )
        keys = referenced | {
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
        environment = {k: project.environment[k] for k in sorted(keys) if k in project.environment}
        user = pwd.getpwuid(os.getuid())
        environment.update(HOME=user.pw_dir, USER=user.pw_name, LOGNAME=user.pw_name)
        environment.setdefault("PATH", os.defpath)
        executable = str(Path(sys.executable).absolute())
        base = (executable, "-m", "rigyard", "--config", str(project.config_path.resolve()))
        start: tuple[str, ...] = (
            *base,
            "scene",
            "autostart",
            "_start",
            scene,
            plan.profile_name,
            "--source",
            str(plan.identity.source_path),
            "--workspace-root",
            str(project.workspace_root),
            "--unit",
            unit,
            "--non-interactive",
        )
        if isolated_socket:
            start += ("--isolated-socket",)
        for path, answer in sorted(answers.items()):
            start += ("--set", f"{path}={json.dumps(answer, ensure_ascii=False)}")
        stop = (*base, "scene", "autostart", "_stop", "--unit", unit)
        # Re-plan against the exact persisted environment; no provider lookup or input allowed.
        replay = self.planner.plan(
            scene,
            plan.profile_name,
            replace(
                request,
                project=replace(project, environment=environment),
                values_path=None,
                overrides=answers,
                interactive=False,
            ),
        )
        if replay != plan:
            raise ScenarioPlanError("autostart environment changes the plan; check HOME/USER/PATH")
        metadata = {
            "unit": unit,
            "config": str(plan.identity.config_path),
            "source": str(plan.identity.source_path),
            "scene": scene,
            "profile": plan.profile_name,
        }
        lines = [
            MARKER + json.dumps(metadata, ensure_ascii=False),
            "[Unit]",
            "Description=Rigyard scenario autostart",
            "Requires=docker.service",
            "After=docker.service network-online.target",
            "Wants=network-online.target",
            "RequiresMountsFor=" + quote(str(project.workspace_root)),
            "",
            "[Service]",
            "Type=oneshot",
            "RemainAfterExit=yes",
            "User=" + scalar(user.pw_name),
            "WorkingDirectory=" + scalar(str(project.workspace_root)),
            *("Environment=" + quote(f"{k}={v}") for k, v in environment.items()),
            "ExecStart=" + command_line(start),
            "ExecStop=" + command_line(stop),
            "ExecStopPost=" + command_line(stop),
            "TimeoutStartSec=infinity",
            "TimeoutStopSec=120",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
        return AutostartPlan(unit, "\n".join(lines), plan)


def preflight(plan: AutostartPlan, manager: SystemdManager) -> None:
    for program in ("systemctl", "systemd-analyze", "docker", "tmux"):
        if shutil.which(program) is None:
            raise ScenarioPlanError(f"autostart requires {program} on the host")
    manager.commands.checked(("docker", "info"), "Docker is unavailable for this user")
    endpoint = os.environ.get("DOCKER_HOST")
    if not endpoint:
        endpoint = manager.commands.checked(
            ("docker", "context", "inspect", "--format={{.Endpoints.docker.Host}}"),
            "cannot inspect Docker context",
        ).stdout.strip()
    if endpoint not in {"unix:///var/run/docker.sock", "unix:///run/docker.sock"}:
        raise ScenarioPlanError("autostart currently requires the local system Docker daemon")
    if plan.scenario.compose is None:
        for instance in plan.scenario.instances:
            assert instance.container is not None
            manager.commands.checked(
                ("docker", "inspect", instance.container),
                f"container {instance.container!r} does not exist",
            )
    else:
        from ..scenarios.executor import ScenarioExecutor

        ScenarioExecutor().compose.preflight(plan.scenario)


def autostart_status(unit: str, manager: SystemdManager) -> str:
    from ..scenarios.lifecycle import ComposeLifecycleBackend
    from ..scenarios.service import ScenarioService

    lines = [f"Unit: {unit}", manager.status(unit)]
    if not (manager.directory / unit).exists():
        return "\n".join(lines)
    metadata = manager.metadata(unit)
    for record in FileRunStore(Path(metadata["config"])).records():
        if record.target.owner_unit != unit:
            continue
        lines.append(f"Recorded state: {record.state}")
        lines.append(ScenarioService().status(record.target).detail)
        if record.target.compose:
            argv = (*ComposeLifecycleBackend._base(record.target), "ps", "--all")
        else:
            argv = (
                "docker",
                "inspect",
                "--format={{.Name}} running={{.State.Running}}",
                *(i.container for i in record.target.instances if i.container),
            )
        lines.append(
            manager.commands.checked(argv, "cannot inspect scene containers").stdout.strip()
        )
        break
    else:
        lines.append("Scene: no recorded run")
    return "\n".join(lines)
