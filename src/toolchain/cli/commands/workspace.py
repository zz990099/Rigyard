"""Workspace initialization command."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...workspace import initialize_workspace
from ..common import print_fields


def register_workspace_commands(commands: Any) -> None:
    initialize = commands.add_parser(
        "init",
        help="bind the current directory to a toolchain configuration",
    )
    initialize.add_argument(
        "-f",
        "--config",
        dest="init_config_path",
        type=Path,
        required=True,
        help="toolchain configuration file to bind",
    )
    initialize.add_argument(
        "--force",
        action="store_true",
        help="replace an existing workspace binding or command alias",
    )
    initialize.add_argument(
        "--alias",
        metavar="NAME",
        help="create a project-local command that uses this configuration",
    )
    initialize.set_defaults(handler=_initialize)


def _initialize(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    result = initialize_workspace(args.init_config_path, force=args.force, alias=args.alias)
    state = "Initialized" if result.changed else "Already initialized"
    fields = [
        f"{state} toolchain workspace: {result.root}",
        f"Configuration: {result.stored_path}",
    ]
    if result.alias_path is not None:
        alias_state = "Created" if result.alias_changed else "Already available"
        fields.append(f"{alias_state} command alias: ./{result.alias_path.name}")
    print_fields(args.style, fields)
    return 0
