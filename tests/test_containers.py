import io
from dataclasses import FrozenInstanceError

import pytest

from toolchain.application.containers import CreateContainerUseCase
from toolchain.application.requests import ParameterRequest
from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.config.loader import load_config
from toolchain.containers.models import ContainerCreateResult, ContainerSpec
from toolchain.containers.planner import ContainerRunPlanner
from toolchain.errors import (
    BackendUnavailableError,
    ContainerCreateError,
    ContainerPlanError,
    SchemaValidationError,
)
from toolchain.parameters.models import ParameterSchema
from toolchain.parameters.resolver import ParameterEngine
from toolchain.providers.docker.container_backend import DockerContainerBackend
from toolchain.providers.docker.runner import CommandResult


def make_plan(tmp_path, **kwargs):
    context = ParameterEngine(ParameterSchema(version=1, parameters={})).resolve(interactive=False)
    return ContainerRunPlanner().plan(
        "dev",
        ContainerSpec(image="ubuntu:24.04", **kwargs),
        context,
        tmp_path / "toolchain.yaml",
        {"DISPLAY": ":0", "USER": "developer"},
    )


class FakeRunner:
    def __init__(self, result=None):
        self.result = result or CommandResult(0, "abc123\n")
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


class FakeBackend:
    def __init__(self):
        self.plans = []

    def create(self, plan):
        self.plans.append(plan)
        return ContainerCreateResult(plan.container_name, "abc123")


def test_defaults_and_immutable_plan(tmp_path):
    plan = make_plan(tmp_path)
    assert DockerContainerBackend().command(plan) == (
        "docker",
        "run",
        "-i",
        "-t",
        "-d",
        "--name=dev",
        "ubuntu:24.04",
    )
    with pytest.raises(FrozenInstanceError):
        plan.image = "other"


@pytest.mark.parametrize("image", ["--privileged", "ubuntu bash", ""])
def test_image_is_a_single_non_option_reference(tmp_path, image):
    context = ParameterEngine(ParameterSchema(version=1, parameters={})).resolve(interactive=False)
    with pytest.raises(ContainerPlanError):
        ContainerRunPlanner().plan(
            "dev", ContainerSpec(image=image), context, tmp_path / "toolchain.yaml", {}
        )


def test_backend_redacts_environment_from_diagnostics(tmp_path):
    runner = FakeRunner(CommandResult(125, stderr="bad value sensitive-token"))
    with pytest.raises(ContainerCreateError) as error:
        DockerContainerBackend(runner).create(
            make_plan(tmp_path, environment={"TOKEN": "sensitive-token"})
        )
    assert "sensitive-token" not in str(error.value)
    assert "<redacted>" in str(error.value)


def test_requested_robot_options(tmp_path):
    plan = make_plan(
        tmp_path,
        privileged=True,
        devices=["/dev/dri"],
        group_add=["video"],
        network="host",
        ipc="host",
        workdir="/workspace",
        mounts=[
            {"source": "..", "target": "/workspace"},
            {"source": "/tmp/.X11-unix", "target": "/tmp/.X11-unix"},
            {"source": "/dev/bus/usb", "target": "/dev/bus/usb"},
        ],
        environment={
            "DISPLAY": {"env": "DISPLAY"},
            "USER": {"env": "USER"},
            "DOCKER_USER": {"env": "USER"},
        },
        command=["/bin/bash"],
    )
    command = DockerContainerBackend().command(plan)
    assert "--privileged" in command
    assert "--device=/dev/dri" in command
    assert "--group-add=video" in command
    assert "--network=host" in command and "--ipc=host" in command
    assert f"--mount=type=bind,source={tmp_path.parent},target=/workspace" in command
    assert "--env=DISPLAY=:0" in command
    assert "--env=DOCKER_USER=developer" in command
    assert command[-2:] == ("ubuntu:24.04", "/bin/bash")


def test_literal_shell_characters_remain_single_arguments(tmp_path):
    plan = make_plan(
        tmp_path,
        environment={"VALUE": "$(touch /tmp/never); x y"},
        command=["echo", "$USER", "a b", "--flag"],
    )
    runner = FakeRunner()
    result = DockerContainerBackend(runner).create(plan)
    assert result.container_id == "abc123"
    command, options = runner.calls[0]
    assert "--env=VALUE=$(touch /tmp/never); x y" in command
    assert command[-4:] == ("echo", "$USER", "a b", "--flag")
    assert options == {"capture": True}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "bad name"},
        {"workdir": "relative"},
        {"devices": ["relative"]},
        {"devices": ["/dev/a:/dev/b:bad"]},
        {"mounts": [{"source": ".", "target": "relative"}]},
        {"mounts": [{"source": "a,b", "target": "/workspace"}]},
        {"mounts": [{"source": ".", "target": "/w"}, {"source": "..", "target": "/w"}]},
        {"environment": {"DISPLAY": {"env": "MISSING"}}},
        {"name": {"parameter": "missing"}},
        {"command": ["a\x00b"]},
    ],
)
def test_invalid_plans_fail_before_docker(tmp_path, kwargs):
    with pytest.raises(ContainerPlanError):
        make_plan(tmp_path, **kwargs)


def test_env_fallback_and_named_volume(tmp_path):
    plan = make_plan(
        tmp_path,
        interactive=False,
        tty=False,
        environment={"EMPTY": {"env": "UNSET", "default": ""}},
        mounts=[{"type": "volume", "source": "cache", "target": "/cache", "read_only": True}],
    )
    command = DockerContainerBackend().command(plan)
    assert "-i" not in command and "-t" not in command and "-d" in command
    assert "--mount=type=volume,source=cache,target=/cache,readonly" in command
    assert "--env=EMPTY=" in command


@pytest.mark.parametrize(
    "body",
    [
        "detach: false",
        "privileged: 'yes'",
        "extra_args: '--rm'",
        "environment: {BAD-NAME: value}",
        "command: /bin/bash",
    ],
)
def test_invalid_schema(tmp_path, body):
    config = tmp_path / "toolchain.yaml"
    config.write_text("version: 1\ncontainers:\n  dev:\n    image: ubuntu\n    " + body + "\n")
    with pytest.raises(SchemaValidationError):
        load_config(config)


def test_conflict_is_reported_without_remove_or_retry(tmp_path):
    runner = FakeRunner(CommandResult(125, stderr="Conflict. The container name is already in use"))
    with pytest.raises(ContainerCreateError, match="Conflict"):
        DockerContainerBackend(runner).create(make_plan(tmp_path))
    assert len(runner.calls) == 1
    assert runner.calls[0][0][:2] == ("docker", "run")


def test_backend_missing_and_empty_id(tmp_path):
    class MissingRunner:
        def run(self, *args, **kwargs):
            raise FileNotFoundError("docker")

    with pytest.raises(BackendUnavailableError):
        DockerContainerBackend(MissingRunner()).create(make_plan(tmp_path))
    with pytest.raises(ContainerCreateError, match="container ID"):
        DockerContainerBackend(FakeRunner(CommandResult(0))).create(make_plan(tmp_path))


def write_config(tmp_path):
    path = tmp_path / "toolchain.yaml"
    path.write_text("""version: 1
parameters:
  name: {type: string, default: default-name}
containers:
  dev:
    name: {parameter: name}
    image: ubuntu:24.04
    environment: {TOKEN: never-print-this}
""")
    return path


def test_cli_dry_run_and_create_uses_default_project_config(tmp_path, monkeypatch, capsys):
    write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr("toolchain.cli.commands.containers.DockerContainerBackend", lambda: backend)
    command = [
        "container",
        "create",
        "dev",
        "--non-interactive",
        "--set",
        "name=chosen",
    ]
    assert run([*command, "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Container: chosen" in output and "never-print-this" not in output
    assert backend.plans == []
    assert run(command) == 0
    assert backend.plans[0].container_name == "chosen"
    assert "Created and started chosen" in capsys.readouterr().out


def test_cli_global_config_selects_project_and_container_key(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr("toolchain.cli.commands.containers.DockerContainerBackend", lambda: backend)

    assert run([
        "--config", str(config), "container", "create", "dev",
        "--non-interactive",
    ]) == 0
    assert backend.plans[0].container_name == "default-name"
    assert "Created and started default-name" in capsys.readouterr().out


def test_unknown_container_and_parameter_priority(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("name: from-values\n")
    monkeypatch.setenv("TOOL_PARAM_NAME", "from-env")
    use_case = CreateContainerUseCase(FakeBackend())
    request = ParameterRequest(
        config, values_path=values, overrides={"name": "from-cli"}, interactive=False
    )
    assert use_case.plan("dev", request).container_name == "from-cli"
    with pytest.raises(SchemaValidationError, match="unknown container"):
        use_case.plan("missing", request)


@pytest.mark.parametrize("answer,expected_calls", [("y", 1), ("n", 0)])
def test_menu_preview_confirmation_and_shared_use_case(tmp_path, answer, expected_calls):
    config = write_config(tmp_path)
    backend = FakeBackend()
    output = io.StringIO()
    app = MenuApp(
        MenuIO(io.StringIO(f"5\n1\n{answer}\n0\n"), output),
        container_backend_factory=lambda: backend,
    )
    assert app.run(config) == 0
    assert len(backend.plans) == expected_calls
    assert "Container: default-name" in output.getvalue()
    assert "never-print-this" not in output.getvalue()
