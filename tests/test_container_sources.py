from rigyard.execution import CommandResult
from rigyard.parameters.sources import PromptSource
from rigyard.providers.docker.containers import (
    CONTAINER_FORMAT,
    PROVIDER_NAME,
    docker_container_sources,
    docker_containers_source,
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


PS_OUTPUT = (
    "other\tup\tubuntu:22.04\n"
    "nhybot_dev_b\texited\tnhybot:base\n"
    "nhybot_dev_a\trunning\tnhybot:base\n"
)


def test_docker_containers_source_filters_and_labels_candidates():
    runner = FakeRunner(CommandResult(0, PS_OUTPUT))
    provider = docker_containers_source(runner)

    options = provider(PromptSource(provider=PROVIDER_NAME, filter="^nhybot_dev_"))

    assert [option.value for option in options] == ["nhybot_dev_a", "nhybot_dev_b"]
    assert options[0].label == "running, nhybot:base"
    assert runner.calls[0][0] == ("docker", "ps", "-a", "--format", CONTAINER_FORMAT)
    assert runner.calls[0][1] == {"capture": True}


def test_docker_containers_source_can_ask_for_running_containers_only():
    runner = FakeRunner(CommandResult(0, PS_OUTPUT))

    docker_containers_source(runner)(PromptSource(provider=PROVIDER_NAME, running_only=True))

    assert runner.calls[0][0] == ("docker", "ps", "--format", CONTAINER_FORMAT)


def test_docker_containers_source_degrades_instead_of_failing():
    for outcome in (
        CommandResult(1, stderr="Cannot connect to the Docker daemon"),
        FileNotFoundError("docker"),
    ):
        assert (
            docker_containers_source(FakeRunner(outcome))(PromptSource(provider=PROVIDER_NAME))
            == ()
        )


def test_docker_container_sources_registers_the_container_provider():
    sources = docker_container_sources(FakeRunner(CommandResult(0, PS_OUTPUT)))

    assert set(sources) == {PROVIDER_NAME}
    options = sources[PROVIDER_NAME](PromptSource(provider=PROVIDER_NAME))
    assert [option.value for option in options] == [
        "nhybot_dev_a",
        "nhybot_dev_b",
        "other",
    ]
