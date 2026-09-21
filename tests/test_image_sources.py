from rigyard.execution import CommandResult
from rigyard.parameters.sources import PromptSource
from rigyard.providers.docker import docker_sources
from rigyard.providers.docker.images import (
    IMAGE_FORMAT,
    PROVIDER_NAME,
    docker_image_sources,
    docker_images_source,
)


class FakeRunner:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


IMAGE_OUTPUT = (
    "ubuntu\t24.04\tsha256:aaaaaaaaaaaaaaaa\t2 weeks ago\t78MB\n"
    "example/robot\tlatest\tsha256:bbbbbbbbbbbbbbbb\t3 hours ago\t4.2GB\n"
    "example/robot\tcuda\tsha256:bbbbbbbbbbbbbbbb\t3 hours ago\t4.2GB\n"
    "<none>\t<none>\tsha256:cccccccccccccccc\t1 minute ago\t4.2GB\n"
)


def test_docker_images_source_filters_labels_sorts_and_omits_dangling_images():
    runner = FakeRunner(CommandResult(0, IMAGE_OUTPUT))
    provider = docker_images_source(runner)

    options = provider(PromptSource(provider=PROVIDER_NAME, filter="^example/robot:"))

    assert [option.value for option in options] == [
        "example/robot:cuda",
        "example/robot:latest",
    ]
    assert options[0].label == "bbbbbbbbbbbb, 3 hours ago, 4.2GB"
    assert runner.calls[0][0] == (
        "docker",
        "image",
        "ls",
        "--no-trunc",
        "--format",
        IMAGE_FORMAT,
    )
    assert runner.calls[0][1] == {"capture": True}


def test_docker_images_source_ignores_malformed_output():
    provider = docker_images_source(FakeRunner(CommandResult(0, "bad-line\n\tlatest\n")))

    assert provider(PromptSource(provider=PROVIDER_NAME)) == ()


def test_docker_images_source_degrades_instead_of_failing():
    for outcome in (
        CommandResult(1, stderr="Cannot connect to the Docker daemon"),
        FileNotFoundError("docker"),
    ):
        assert docker_images_source(FakeRunner(outcome))(
            PromptSource(provider=PROVIDER_NAME)
        ) == ()


def test_docker_source_registries_include_image_and_container_providers():
    runner = FakeRunner(CommandResult(0, IMAGE_OUTPUT))

    assert set(docker_image_sources(runner)) == {"docker-images"}
    assert set(docker_sources(runner)) == {"docker-containers", "docker-images"}
