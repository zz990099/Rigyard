"""Command-line composition root."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ..errors import RigyardError
from ..version import __version__
from ..workspace import resolve_config_path
from .commands.builds import register_build_commands
from .commands.containers import register_container_commands
from .commands.images import register_image_commands
from .commands.parameters import register_parameter_commands
from .commands.scenarios import register_scenario_commands
from .commands.tasks import register_task_commands
from .commands.tests import register_test_commands
from .commands.workspace import register_workspace_commands
from .common import stream_input
from .menu import MenuApp, MenuIO
from .style import ColorMode, Style


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rigyard",
        description="Configuration-driven container development workflows.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-f",
        "--config",
        dest="config_path",
        type=Path,
        default=None,
        help="Rigyard configuration file (overrides workspace initialization)",
    )
    parser.add_argument(
        "--values",
        type=Path,
        default=None,
        help="optional values file used by the interactive menu",
    )
    parser.add_argument(
        "--color",
        choices=[mode.value for mode in ColorMode],
        default=ColorMode.AUTO.value,
        help="colour the terminal output (auto: only when the stream is a terminal)",
    )
    commands = parser.add_subparsers(dest="command")
    register_workspace_commands(commands)
    register_parameter_commands(commands)
    register_image_commands(commands)
    register_container_commands(commands)
    register_build_commands(commands)
    register_scenario_commands(commands)
    register_test_commands(commands)
    register_task_commands(commands)
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
    style = Style.for_stream(output_stream, mode=args.color)
    error_style = Style.for_stream(error_stream, mode=args.color)
    args.style = style
    args.output = output_stream
    args.error = error_stream
    args.input_fn = stream_input(input_stream, output_stream)
    try:
        if args.command is None:
            io = MenuIO(input_stream, output_stream, style=style)
            if not io.is_interactive:
                parser.print_help(file=output_stream)
                return 2
            args.config_path = resolve_config_path(args.config_path)
            return MenuApp(io).run(args.config_path, args.values)
        if args.command != "init":
            args.config_path = resolve_config_path(args.config_path)
        return args.handler(args, parser)
    except RigyardError as exc:
        print(error_style.render("error", f"Error: {exc}"), file=error_stream)
        return exc.exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
