"""Docker CLI provider."""

from .build_backend import DockerExecBuildBackend
from .container_backend import DockerContainerBackend
from .containers import docker_container_sources, docker_containers_source
from .image_backend import DockerImageBackend
from .images import docker_image_sources, docker_images_source
from .sources import docker_sources
from .task_backend import DockerExecTaskBackend
from .test_backend import DockerExecTestBackend

__all__ = [
    "DockerContainerBackend",
    "DockerExecBuildBackend",
    "DockerImageBackend",
    "DockerExecTestBackend",
    "DockerExecTaskBackend",
    "docker_container_sources",
    "docker_containers_source",
    "docker_image_sources",
    "docker_images_source",
    "docker_sources",
]
