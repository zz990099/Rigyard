"""Command-line composition root."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ..errors import ToolchainError
from ..version import __version__
from .commands.containers import register_container_commands
from .commands.images import register_image_commands
from .commands.parameters import register_parameter_commands
from .menu import MenuApp, MenuIO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolchain",
        description="Configuration-driven development toolchain.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-f",
        "--config",
        dest="menu_config",
        type=Path,
        default=Path("toolchain.yaml"),
        help="configuration file used by the interactive menu",
    )
    parser.add_argument(
        "--values",
        type=Path,
        default=None,
        help="optional values file used by the interactive menu",
    )
    commands = parser.add_subparsers(dest="command")
    register_parameter_commands(commands)
    register_image_commands(commands)
    register_container_commands(commands)
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        if args.command is None:
            io = MenuIO(input_stream, output_stream)
            if not io.is_interactive:
                parser.print_help(file=output_stream)
                return 2
            return MenuApp(io).run(args.menu_config, args.values)
        return args.handler(args, parser)
    except ToolchainError as exc:
        print(f"Error: {exc}", file=error_stream)
        return exc.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
