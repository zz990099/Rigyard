"""Command-line composition root."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ..errors import ToolchainError
from ..version import __version__
from .commands.parameters import register_parameter_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolchain",
        description="Configuration-driven development toolchain.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    register_parameter_commands(commands)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args, parser)
    except ToolchainError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()

