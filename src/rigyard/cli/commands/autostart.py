"""CLI and systemd entry points for scenario autostart."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any

from ...application.autostart import PlanAutostartUseCase, preflight, selected_unit, unit_name
from ...application.scenarios import PlanScenarioUseCase
from ...autostart.systemd import SystemdManager, validate_unit
from ...errors import ScenarioPlanError
from ...providers.docker import docker_sources
from ...scenarios.records import FileRunStore
from ...scenarios.service import ScenarioService
from .parameters import add_resolution_arguments, resolution_request


def register_autostart_commands(actions: Any) -> None:
    command = actions.add_parser("autostart", help="manage scenario boot registration")
    commands = command.add_subparsers(dest="autostart_command", required=True)
    for name in ("enable", "disable", "status", "_start", "_stop"):
        parser = commands.add_parser(
            name, help=(argparse.SUPPRESS if name.startswith("_") else f"{name} scenario autostart")
        )
        parser.add_argument("scene_name", nargs="?")
        parser.add_argument("profile_name", nargs="?")
        parser.add_argument("--source", type=Path)
        parser.add_argument("--unit", help="registered unit name (also works after YAML removal)")
        parser.add_argument("--workspace-root", type=Path, dest="autostart_workspace")
        if name in {"enable", "_start"}:
            add_resolution_arguments(parser)
            parser.add_argument(
                "--isolated-socket", action="store_true", help="use a dedicated tmux server socket"
            )
        if name == "enable":
            parser.add_argument("--dry-run", action="store_true")
        if name in {"enable", "disable"}:
            parser.add_argument("--now", action="store_true")
        parser.set_defaults(handler=_handle)


def _handle(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    action = args.autostart_command
    if args.autostart_workspace is not None:
        args.workspace_root = args.autostart_workspace
    manager = SystemdManager()
    if action in {"enable", "_start"}:
        if not args.scene_name:
            parser.error("scene name is required")
        request = resolution_request(args, parser)
        if action == "enable":
            if args.unit:
                parser.error("enable derives --unit from the selected scenario")
            planned = PlanAutostartUseCase(docker_sources(), args.style.render).plan(
                args.scene_name, args.profile_name, request, isolated_socket=args.isolated_socket
            )
            if args.dry_run:
                print(planned.content, file=args.output)
            else:
                preflight(planned, manager)
                manager.install(planned.unit, planned.content, now=args.now)
                print(
                    f"Enabled {planned.unit}"
                    + (" and started" if args.now else " (next boot; current run unchanged)"),
                    file=args.output,
                )
            return 0
        # This entry point is invoked by the generated system service, never prompts/attaches.
        plan = PlanScenarioUseCase().plan(
            args.scene_name, args.profile_name, replace(request, interactive=False)
        )
        assert plan.identity is not None
        expected = unit_name(plan.identity)
        if args.unit != expected:
            raise ScenarioPlanError("autostart unit does not match scenario identity")
        plan = replace(
            plan,
            owner_unit=expected,
            tmux_socket=expected.removesuffix(".service") if args.isolated_socket else None,
            attach=False,
        )
        ScenarioService(owner_unit=expected).start(plan)
        return 0

    unit = args.unit
    if unit is None:
        if not args.scene_name:
            parser.error("provide a scene name or --unit")
        from ...application.requests import ResolutionRequest

        unit = selected_unit(
            args.scene_name,
            args.profile_name,
            ResolutionRequest(
                args.config_path,
                source_path=args.source,
                interactive=False,
                workspace_root=args.workspace_root,
            ),
        )
    validate_unit(unit)
    if action == "_stop":
        # Never re-plan from modified YAML, and never stop a later manual run.
        for record in FileRunStore(args.config_path).records():
            if record.target.owner_unit == unit:
                ScenarioService(owner_unit=unit).stop(record.target)
        return 0
    if action == "disable":
        manager.disable(unit, now=args.now)
        print(
            f"Disabled {unit}" + (" and stopped" if args.now else " (current run unchanged)"),
            file=args.output,
        )
        return 0
    from ...application.autostart import autostart_status

    print(autostart_status(unit, manager), file=args.output)
    return 0
