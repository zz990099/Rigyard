"""CLI entry points for starting and managing named scenarios."""

from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Any

from ...application.requests import ResolutionRequest
from ...application.scenarios import PlanScenarioUseCase
from ...scenarios.models import ScenarioPlan
from ...scenarios.service import ScenarioService
from ..common import parse_overrides
from ..scenario_output import describe_scenario
from .parameters import add_resolution_arguments


def register_scenario_commands(commands: Any) -> None:
    scene = commands.add_parser("scene", help="start and manage scenarios")
    actions = scene.add_subparsers(dest="scene_command", required=True)

    start = _operation(actions, "start", "start a scenario profile")
    start.add_argument("--dry-run", action="store_true", help="show the plan without starting")
    start.add_argument("--replace", action="store_true", help="replace an existing tmux session")
    start.add_argument(
        "--no-attach",
        action="store_true",
        help="do not attach after starting a tmux profile",
    )
    start.set_defaults(handler=_start)

    stop = _operation(actions, "stop", "stop a scenario profile")
    stop.set_defaults(handler=_stop)
    down = _operation(actions, "down", "stop a scenario and remove its Compose environment")
    down.set_defaults(handler=_down)
    status = _operation(actions, "status", "show scenario status")
    status.set_defaults(handler=_status)

    attach = _operation(actions, "attach", "attach to a running tmux scenario")
    attach.add_argument("--group", help="select the initial tmux pane (group)")
    attach.set_defaults(handler=_attach)

    logs = _operation(actions, "logs", "show scenario logs")
    logs.add_argument("--group", help="show one scenario group")
    logs.add_argument("--follow", action="store_true", help="follow logs interactively")
    logs.set_defaults(handler=_logs)


def _operation(actions: Any, name: str, help_text: str) -> argparse.ArgumentParser:
    command = actions.add_parser(name, help=help_text)
    command.add_argument("scene_name", help="scenario configuration name under scenarios")
    command.add_argument("profile_name", help="profile name under the selected scenario")
    command.add_argument(
        "--instance",
        dest="instances",
        action="append",
        metavar="NAME",
        help="run one scenario instance; repeat to select several (default: all enabled)",
    )
    add_resolution_arguments(command)
    return command


def _plan(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> ScenarioPlan:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    return PlanScenarioUseCase().plan(
        args.scene_name,
        args.profile_name,
        ResolutionRequest(
            args.config_path,
            args.values,
            overrides,
            interactive=not args.non_interactive,
        ),
        resolve_group_runtime=args.scene_command == "start",
        instances=args.instances,
    )


def _service() -> ScenarioService:
    return ScenarioService()


def _start(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _plan(args, parser)
    if args.replace or args.no_attach:
        plan = replace(
            plan,
            replace=plan.replace or args.replace,
            attach=plan.attach and not args.no_attach,
        )
    if args.dry_run:
        print("\n".join(describe_scenario(plan)))
        return 0
    result = _service().start(plan)
    print(f"Started scenario {result.scene_name!r} profile {result.profile_name!r}")
    return 0


def _stop(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _plan(args, parser)
    result = _service().stop(plan)
    print(result.detail or f"Stopped scenario {result.scene_name!r}")
    return 0


def _down(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.instances:
        parser.error("scene down does not support --instance")
    plan = _plan(args, parser)
    result = _service().down(plan)
    print(result.detail or f"Removed scenario {result.scene_name!r} environment")
    return 0


def _status(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _plan(args, parser)
    result = _service().status(plan)
    print(result.detail or "running")
    return 0


def _attach(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _plan(args, parser)
    result = _service().attach(plan, args.instance, args.group)
    if result.detail:
        print(result.detail)
    return 0


def _logs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _plan(args, parser)
    result = _service().logs(plan, args.instance, args.group, follow=args.follow)
    if result.detail:
        print(result.detail)
    return 0
