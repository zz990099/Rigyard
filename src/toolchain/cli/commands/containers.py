"""Scriptable container creation frontend."""

from __future__ import annotations

import argparse
from typing import Any

from ...application.containers import CreateContainerUseCase
from ...application.requests import ResolutionRequest
from ...providers.docker.container_backend import DockerContainerBackend
from ..common import parse_overrides
from ..container_output import describe_container
from .parameters import add_resolution_arguments


def register_container_commands(commands: Any) -> None:
    container = commands.add_parser("container", help="create and start containers")
    actions = container.add_subparsers(dest="container_command", required=True)
    create = actions.add_parser("create", help="create and start a new detached container")
    create.add_argument(
        "container_name",
        help="container configuration name under the top-level containers mapping",
    )
    create.add_argument("--dry-run", action="store_true", help="show a plan without running Docker")
    add_resolution_arguments(create)
    create.set_defaults(handler=_create)


def _create(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    use_case = CreateContainerUseCase(DockerContainerBackend())
    plan = use_case.plan(
        args.container_name,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
        ),
    )
    if args.dry_run:
        print("\n".join(describe_container(plan)))
        return 0
    result = use_case.execute(plan)
    print(f"Created and started {result.container_name} ({result.container_id})")
    return 0
