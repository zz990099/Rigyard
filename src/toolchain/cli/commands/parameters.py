"""CLI commands provided by the declarative parameter subsystem."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...config.loader import load_schema, load_values
from ...parameters.context import ResolvedContext
from ...parameters.resolver import ParameterEngine
from ..common import emit, parse_overrides


def register_parameter_commands(commands: Any) -> None:
    validate = commands.add_parser("validate", help="validate a parameter schema")
    validate.add_argument("schema", type=Path)
    validate.set_defaults(handler=_validate)

    inspect = commands.add_parser("inspect", help="show dependencies and resolution order")
    inspect.add_argument("schema", type=Path)
    inspect.add_argument("--format", choices=("json", "yaml"), default="yaml")
    inspect.set_defaults(handler=_inspect)

    resolve = commands.add_parser("resolve", help="resolve parameters from all input layers")
    resolve.add_argument("schema", type=Path)
    add_resolution_arguments(resolve)
    resolve.add_argument("--with-sources", action="store_true")
    resolve.add_argument("--format", choices=("json", "yaml"), default="yaml")
    resolve.set_defaults(handler=_resolve)


def add_resolution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--values", type=Path, help="optional YAML values mapping")
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override one value; repeat as needed",
    )
    parser.add_argument("--non-interactive", action="store_true")


def resolve_context(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> ResolvedContext:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    values = load_values(args.values) if args.values else {}
    return ParameterEngine(load_schema(args.schema)).resolve(
        values=values,
        overrides=overrides,
        interactive=not args.non_interactive,
    )


def _validate(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    ParameterEngine(load_schema(args.schema))
    print(f"OK: {args.schema}")
    return 0


def _inspect(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    engine = ParameterEngine(load_schema(args.schema))
    emit(engine.inspect(), args.format)
    return 0


def _resolve(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    context = resolve_context(args, parser)
    output = context.as_dict(include_sources=args.with_sources)
    if context.disabled:
        output["_disabled"] = sorted(context.disabled)
    emit(output, args.format)
    return 0

