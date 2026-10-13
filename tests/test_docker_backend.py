import os
from pathlib import Path

import pytest

from rigyard.errors import BackendUnavailableError, ImageBuildError
from rigyard.execution import CommandResult
from rigyard.images.models import ImageBuildStep
from rigyard.providers.docker.image_backend import DockerImageBackend


class FakeRunner:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def run(self, command, *, stdin=None, capture=False, environment=None):
        self.calls.append((command, stdin, capture, environment))
        return next(self.results)


def step(network=None) -> ImageBuildStep:
    return ImageBuildStep(
        index=1,
        layer_name="system",
        base_image="ubuntu:22.04",
        output_tag="example/test:latest",
        context=Path("/project"),
        dockerfile_fragment="RUN echo ok\n",
        build_args={"MODE": "release", "ZERO": "0"},
        network=network,
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


def test_backend_adds_configured_build_network() -> None:
    runner = FakeRunner([CommandResult(0)])
    DockerImageBackend(runner).build_step(step("host"))
    command = runner.calls[0][0]
    network_index = command.index("--network")
    assert command[network_index + 1] == "host"


def test_unavailable_daemon_has_backend_error() -> None:
    backend = DockerImageBackend(FakeRunner([CommandResult(1, stderr="cannot connect")]))
    with pytest.raises(BackendUnavailableError, match="cannot connect"):
        backend.check_available()


@pytest.mark.parametrize(
    ("method", "message"),
    [("check_available", "cannot execute Docker"), ("build_step", "cannot execute Docker build")],
)
def test_os_errors_are_normalized_as_backend_errors(method, message) -> None:
    class BrokenRunner:
        def run(self, *_args, **_kwargs):
            raise PermissionError("permission denied")

    backend = DockerImageBackend(BrokenRunner())
    with pytest.raises(BackendUnavailableError, match=f"{message}.*permission denied"):
        if method == "check_available":
            backend.check_available()
        else:
            backend.build_step(step())


def test_failed_layer_has_build_context() -> None:
    backend = DockerImageBackend(FakeRunner([CommandResult(9, stderr="build failed")]))
    with pytest.raises(ImageBuildError, match="layer 1 .*system.*exit 9.*build failed"):
        backend.build_step(step())


@pytest.mark.parametrize("code", [0, 1])
def test_tag_alias_uses_argv_and_reports_failure(code):
    runner = FakeRunner([CommandResult(code, stderr="tag failed" if code else "")])
    backend = DockerImageBackend(runner)
    if code:
        with pytest.raises(ImageBuildError, match="was built but tagging alias"):
            backend.tag_image("example:test-date", "example:stable")
    else:
        backend.tag_image("example:test-date", "example:stable")
    assert runner.calls[0][0] == ("docker", "tag", "example:test-date", "example:stable")


@pytest.mark.parametrize("existing", [None, "0", "1"])
def test_build_disables_default_attestations_without_changing_host_environment(
    monkeypatch, existing
):
    variable = "BUILDX_NO_DEFAULT_ATTESTATIONS"
    if existing is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, existing)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/rigyard-test-docker.sock")
    monkeypatch.setenv("HTTP_PROXY", "http://localhost:3128")
    original = dict(os.environ)
    runner = FakeRunner([CommandResult(0), CommandResult(0), CommandResult(0)])
    backend = DockerImageBackend(runner)
    backend.check_available()
    backend.build_step(step())
    backend.tag_image("example/test:latest", "example/test:alias")
    check_call, build_call, tag_call = runner.calls
    assert check_call[3] is None
    assert tag_call[3] is None
    assert build_call[3] == {**original, variable: "1"}
    assert dict(os.environ) == original
    assert not any(argument.startswith("--provenance") for argument in build_call[0])
