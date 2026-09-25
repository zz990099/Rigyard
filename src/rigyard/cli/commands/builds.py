"""CLI entry point for configured project builds."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.builds import BuildProjectUseCase
from ...application.requests import ResolutionRequest
from ...providers.docker import DockerExecBuildBackend, docker_sources
from ..build_output import describe_build
from ..common import parse_overrides, print_fields, say
from .parameters import add_resolution_arguments


def register_build_commands(commands: Any) -> None:
    build = commands.add_parser("build", help="run a configured project build")
    build.add_argument("build_name", help="build configuration name under builds")
    build.add_argument("--source", type=Path, help="source file for ambiguous build names")
    build.add_argument("--dry-run", action="store_true", help="show the plan without executing it")
    add_resolution_arguments(build)
    build.set_defaults(handler=_build)


def _build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    use_case = BuildProjectUseCase(
        DockerExecBuildBackend(),
        sources=docker_sources(),
        formatter=args.style.render,
    )
    plan = use_case.plan(
        args.build_name,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
            input_fn=args.input_fn,
            source_path=args.source,
            workspace_root=args.workspace_root,
        ),
    )
    if args.dry_run:
        print_fields(args.style, describe_build(plan), stream=args.output)
        return 0
    result = use_case.execute(plan)
    say(args.style, f"Build {result.build_name!r} completed", stream=args.output)
    return 0
