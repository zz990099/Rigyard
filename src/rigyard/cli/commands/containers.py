"""Scriptable container creation frontend."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.containers import CreateContainerUseCase
from ...application.requests import ResolutionRequest
from ...providers.docker import docker_sources
from ...providers.docker.container_backend import DockerContainerBackend
from ..common import parse_overrides, print_fields, say
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
    create.add_argument("--source", type=Path, help="source file for ambiguous container names")
    add_resolution_arguments(create)
    create.set_defaults(handler=_create)


def _create(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    def confirm_replace(message: str) -> bool:
        if args.non_interactive:
            print(f"{message} [y/N]: N (non-interactive)")
            return False
        try:
            return input(f"{message} [y/N]: ").strip().lower() in {"y", "yes"}
        except EOFError:
            return False

    use_case = CreateContainerUseCase(
        DockerContainerBackend(confirm_replace=confirm_replace),
        sources=docker_sources(),
        formatter=args.style.render,
    )
    plan = use_case.plan(
        args.container_name,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
            source_path=args.source,
        ),
    )
    if args.dry_run:
        print_fields(args.style, describe_container(plan))
        return 0
    result = use_case.execute(plan)
    say(
        args.style,
        f"Created and started {result.container_name} ({result.container_id}); "
        f"completed {len(result.hooks)} lifecycle hook(s)",
    )
    return 0
