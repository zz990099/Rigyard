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
        help="bind the current directory to a Rigyard configuration",
    )
    initialize.add_argument(
        "-f",
        "--config",
        dest="init_config_path",
        type=Path,
        required=True,
        help="Rigyard configuration file to bind",
    )
    initialize.add_argument(
        "--force",
        action="store_true",
        help="replace an existing workspace binding or command alias",
    )
    alias_options = initialize.add_mutually_exclusive_group()
    alias_options.add_argument(
        "--alias",
        metavar="NAME",
        help="override the project-local command alias configured by the manifest",
    )
    alias_options.add_argument(
        "--no-alias",
        action="store_true",
        help="do not create the command alias configured by the manifest",
    )
    initialize.set_defaults(handler=_initialize)


def _initialize(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    result = initialize_workspace(
        args.init_config_path,
        force=args.force,
        alias=args.alias,
        use_config_alias=not args.no_alias,
    )
    state = "Initialized" if result.changed else "Already initialized"
    fields = [
        f"{state} Rigyard workspace: {result.root}",
        f"Configuration: {result.stored_path}",
    ]
    if result.alias_path is not None:
        alias_state = "Created" if result.alias_changed else "Already available"
        fields.extend(
            (
                f"{alias_state} environment command alias: {result.alias_path}",
                f"Available while this Python environment is active: {result.alias_path.name}",
            )
        )
    print_fields(args.style, fields)
    return 0
