"""Registry for Docker-backed dynamic prompt sources."""

from __future__ import annotations

from ...execution import CommandRunner
from ...parameters.sources import DynamicOptionsProvider
from .containers import docker_container_sources
from .images import docker_image_sources


def docker_sources(
    runner: CommandRunner | None = None,
) -> dict[str, DynamicOptionsProvider]:
    """Return every built-in Docker-backed dynamic options provider."""

    return {
        **docker_container_sources(runner),
        **docker_image_sources(runner),
    }
