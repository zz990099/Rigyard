"""Command-line interface for schema validation, inspection, and resolution."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from .engine import ParameterEngine
from .errors import ToolchainError
from .loader import load_schema, load_values


def _overrides(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"invalid --set {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if not name:
            raise argparse.ArgumentTypeError("--set parameter name must not be empty")
        result[name] = value
    return result


def _serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    return value


def _emit(data: Any, output_format: str) -> None:
    normalized = _serializable(data)
    if output_format == "json":
        print(json.dumps(normalized, indent=2, ensure_ascii=False))
    else:
        print(yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True).rstrip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolchain",
        description="Validate and resolve YAML v1 declarative parameters.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a parameter schema")
    validate.add_argument("schema", type=Path)

    inspect = commands.add_parser("inspect", help="show dependencies and resolution order")
    inspect.add_argument("schema", type=Path)
    inspect.add_argument("--format", choices=("json", "yaml"), default="yaml")

    resolve = commands.add_parser("resolve", help="resolve parameters from all input layers")
    resolve.add_argument("schema", type=Path)
    resolve.add_argument("--values", type=Path, help="optional YAML values mapping")
    resolve.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override one value; repeat as needed",
    )
    resolve.add_argument("--non-interactive", action="store_true")
    resolve.add_argument("--with-sources", action="store_true")
    resolve.add_argument("--format", choices=("json", "yaml"), default="yaml")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        engine = ParameterEngine(load_schema(args.schema))
        if args.command == "validate":
            print(f"OK: {args.schema}")
            return 0
        if args.command == "inspect":
            _emit(engine.inspect(), args.format)
            return 0

        try:
            overrides = _overrides(args.sets)
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
        values = load_values(args.values) if args.values else {}
        context = engine.resolve(
            values=values,
            overrides=overrides,
            interactive=not args.non_interactive,
        )
        output = context.as_dict(include_sources=args.with_sources)
        if context.disabled:
            output["_disabled"] = sorted(context.disabled)
        _emit(output, args.format)
        return 0
    except ToolchainError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()

