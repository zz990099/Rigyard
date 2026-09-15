"""CLI entry point for configured project builds."""

from __future__ import annotations

import argparse
from typing import Any

from ...application.builds import BuildProjectUseCase
from ...application.requests import ResolutionRequest
from ...providers.host import HostBuildBackend
from ..build_output import describe_build
from ..common import parse_overrides
from .parameters import add_resolution_arguments


def register_build_commands(commands: Any) -> None:
    build = commands.add_parser("build", help="run a configured project build")
    build.add_argument("build_name", help="build configuration name under builds")
    build.add_argument("--dry-run", action="store_true", help="show the plan without executing it")
    add_resolution_arguments(build)
    build.set_defaults(handler=_build)


def _build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    use_case = BuildProjectUseCase(HostBuildBackend())
    plan = use_case.plan(
        args.build_name,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
        ),
    )
    if args.dry_run:
        print("\n".join(describe_build(plan)))
        return 0
    result = use_case.execute(plan)
    print(f"Build {result.build_name!r} completed")
    return 0
