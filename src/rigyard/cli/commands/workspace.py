"""Workspace initialization command."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...config.loader import load_config
from ...workspace import ConfigResolution, initialize_workspace, remove_environment_alias
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
        help="override the environment command alias configured by the manifest",
    )
    alias_options.add_argument(
        "--no-alias",
        action="store_true",
        help="do not create the command alias configured by the manifest",
    )
    initialize.set_defaults(handler=_initialize)

    context = commands.add_parser(
        "context",
        help="show how the active configuration was selected",
    )
    context.set_defaults(handler=_show_context)

    alias = commands.add_parser(
        "alias",
        help="manage a Rigyard environment command alias",
    )
    alias_commands = alias.add_subparsers(dest="alias_command", required=True)
    remove = alias_commands.add_parser(
        "remove",
        help="remove a Rigyard-generated alias",
    )
    remove.add_argument(
        "name",
        nargs="?",
        help="alias name; defaults to workspace.command_alias",
    )
    remove.set_defaults(handler=_remove_alias)


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
    print_fields(args.style, fields, stream=args.output)
    return 0


def _remove_alias(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    result = remove_environment_alias(
        args.config_path,
        args.name,
        workspace_root=args.workspace_root,
    )
    message = (
        f"Removed environment command alias: {result.path}"
        if result.removed
        else f"Environment command alias already absent: {result.path}"
    )
    print_fields(args.style, (message,), stream=args.output)
    return 0


def _show_context(args: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    resolution: ConfigResolution = args.config_resolution
    config = load_config(
        resolution.config_path,
        workspace_root=resolution.workspace_root,
    )
    fields = [
        f"Current directory: {resolution.current_directory}",
        f"Resolution source: {resolution.source}",
        f"Workspace root: {resolution.workspace_root}",
    ]
    if resolution.workspace_marker is not None:
        fields.append(f"Workspace marker: {resolution.workspace_marker}")
    fields.append(f"Configuration: {resolution.config_path}")
    for kind, groups in config.source_files.items():
        fields.extend(f"Source [{kind}]: {group.path}" for group in groups)
    print_fields(args.style, fields, stream=args.output)
    return 0
