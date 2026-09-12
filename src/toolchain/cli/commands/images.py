"""CLI entry point for layered image builds."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...config.loader import load_config, load_values
from ...errors import ImageConfigError
from ...images.service import ImageBuildService
from ...parameters.resolver import ParameterEngine
from ...providers.docker import DockerImageBackend
from ..common import parse_overrides
from .parameters import add_resolution_arguments


def register_image_commands(commands: Any) -> None:
    image = commands.add_parser("image", help="build and manage images")
    actions = image.add_subparsers(dest="image_command", required=True)

    build = actions.add_parser("build", help="build one layered image")
    build.add_argument("schema", type=Path)
    build.add_argument("image_name")
    add_resolution_arguments(build)
    build.set_defaults(handler=_build)


def _build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config = load_config(args.schema)
    if args.image_name not in config.images:
        available = ", ".join(sorted(config.images)) or "none"
        raise ImageConfigError(
            f"unknown image {args.image_name!r}; configured images: {available}"
        )
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    values = load_values(args.values) if args.values else {}
    context = ParameterEngine(config.parameter_schema()).resolve(
        values=values,
        overrides=overrides,
        interactive=not args.non_interactive,
    )
    result = ImageBuildService(DockerImageBackend()).build(
        args.image_name,
        config.images[args.image_name],
        context,
        args.schema,
    )
    print(f"Built {result.final_tag} ({len(result.steps)} layer(s))")
    return 0

