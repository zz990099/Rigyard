"""Command-line composition root."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ..errors import ToolchainError
from ..version import __version__
from ..workspace import resolve_config_path
from .commands.builds import register_build_commands
from .commands.containers import register_container_commands
from .commands.images import register_image_commands
from .commands.parameters import register_parameter_commands
from .commands.scenarios import register_scenario_commands
from .commands.workspace import register_workspace_commands
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
        dest="config_path",
        type=Path,
        default=None,
        help="toolchain configuration file (overrides workspace initialization)",
    )
    parser.add_argument(
        "--values",
        type=Path,
        default=None,
        help="optional values file used by the interactive menu",
    )
    commands = parser.add_subparsers(dest="command")
    register_workspace_commands(commands)
    register_parameter_commands(commands)
    register_image_commands(commands)
    register_container_commands(commands)
    register_build_commands(commands)
    register_scenario_commands(commands)
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
            args.config_path = resolve_config_path(args.config_path)
            return MenuApp(io).run(args.config_path, args.values)
        if args.command != "init":
            args.config_path = resolve_config_path(args.config_path)
        return args.handler(args, parser)
    except ToolchainError as exc:
        print(f"Error: {exc}", file=error_stream)
        return exc.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
