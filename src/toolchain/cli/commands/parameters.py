"""Project validation and inline runtime-value inspection commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.parameters import (
    InspectParametersUseCase,
    ResolveParametersUseCase,
    ValidateConfigUseCase,
)
from ...application.requests import ResolutionRequest
from ...providers.docker import docker_container_sources
from ..common import emit, parse_overrides


def register_parameter_commands(commands: Any) -> None:
    validate = commands.add_parser("validate", help="validate the toolchain configuration")
    validate.set_defaults(handler=_validate)
    inspect = commands.add_parser("inspect", help="show inline runtime prompts")
    inspect.add_argument("--format", choices=("json", "yaml"), default="yaml")
    inspect.set_defaults(handler=_inspect)
    resolve = commands.add_parser("resolve", help="resolve all inline runtime prompts")
    add_resolution_arguments(resolve)
    resolve.add_argument("--with-sources", action="store_true")
    resolve.add_argument("--format", choices=("json", "yaml"), default="yaml")
    resolve.set_defaults(handler=_resolve)


def add_resolution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--values", type=Path, default=argparse.SUPPRESS, help="optional YAML values tree"
    )
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="override an inline value by configuration path; repeat as needed",
    )
    parser.add_argument("--non-interactive", action="store_true")


def resolution_request(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> ResolutionRequest:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    return ResolutionRequest(
        args.config_path,
        args.values,
        overrides,
        interactive=not args.non_interactive,
    )


def _validate(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    ValidateConfigUseCase().execute(args.config_path)
    print(f"OK: {args.config_path}")
    return 0


def _inspect(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    emit(InspectParametersUseCase().execute(args.config_path), args.format)
    return 0


def _resolve(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    context = ResolveParametersUseCase(sources=docker_container_sources()).execute(
        resolution_request(args, parser)
    )
    emit(context.as_dict(include_sources=args.with_sources), args.format)
    return 0
