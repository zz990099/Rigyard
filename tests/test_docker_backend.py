from pathlib import Path

import pytest

from toolchain.errors import BackendUnavailableError, ImageBuildError
from toolchain.images.models import ImageBuildStep
from toolchain.providers.docker.image_backend import DockerImageBackend
from toolchain.providers.docker.runner import CommandResult


class FakeRunner:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def run(self, command, *, stdin=None, capture=False):
        self.calls.append((command, stdin, capture))
        return next(self.results)


def step() -> ImageBuildStep:
    return ImageBuildStep(
        index=1,
        layer_name="system",
        base_image="ubuntu:22.04",
        output_tag="example/test:latest",
        context=Path("/project"),
        dockerfile_fragment="RUN echo ok\n",
        build_args={"MODE": "release", "ZERO": "0"},
    )


def test_backend_checks_daemon_and_builds_without_shell() -> None:
    runner = FakeRunner([CommandResult(0, "27.0"), CommandResult(0)])
    backend = DockerImageBackend(runner)
    backend.check_available()
    result = backend.build_step(step())
    check_call, build_call = runner.calls
    assert check_call[0] == ("docker", "version", "--format", "{{.Server.Version}}")
    assert check_call[2] is True
    assert build_call[0] == (
        "docker",
        "build",
        "--file",
        "-",
        "--tag",
        "example/test:latest",
        "--build-arg",
        "MODE=release",
        "--build-arg",
        "ZERO=0",
        "/project",
    )
    assert build_call[1] == "FROM ubuntu:22.04\n\nRUN echo ok\n"
    assert result.output_tag == "example/test:latest"


def test_unavailable_daemon_has_backend_error() -> None:
    backend = DockerImageBackend(FakeRunner([CommandResult(1, stderr="cannot connect")]))
    with pytest.raises(BackendUnavailableError, match="cannot connect"):
        backend.check_available()


def test_failed_layer_has_build_context() -> None:
    backend = DockerImageBackend(FakeRunner([CommandResult(9, stderr="build failed")]))
    with pytest.raises(ImageBuildError, match="layer 1 .*system.*exit 9.*build failed"):
        backend.build_step(step())

