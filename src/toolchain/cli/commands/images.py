"""CLI entry point for layered image builds."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.images import BuildImageUseCase
from ...application.requests import BuildImageRequest
from ...providers.docker import DockerImageBackend, docker_container_sources
from ..common import parse_overrides
from .parameters import add_resolution_arguments


def register_image_commands(commands: Any) -> None:
    image = commands.add_parser("image", help="build and manage images")
    actions = image.add_subparsers(dest="image_command", required=True)

    build = actions.add_parser("build", help="build one layered image")
    build.add_argument("image_name", help="image configuration name under images")
    build.add_argument("--source", type=Path, help="source file for ambiguous image names")
    add_resolution_arguments(build)
    build.set_defaults(handler=_build)


def _build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    use_case = BuildImageUseCase(DockerImageBackend(), sources=docker_container_sources())
    plan = use_case.plan(
        BuildImageRequest(
            config_path=args.config_path,
            image_name=args.image_name,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
            source_path=args.source,
        )
    )
    result = use_case.execute(plan)
    print(f"Built {result.final_tag} ({len(result.steps)} layer(s))")
    if result.tag_alias is not None:
        print(f"Alias: {result.tag_alias}")
    return 0
