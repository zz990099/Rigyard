import io
from dataclasses import FrozenInstanceError

import pytest

from toolchain.application.containers import CreateContainerUseCase
from toolchain.application.requests import ResolutionRequest
from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.containers.models import ContainerCreateResult, ContainerSpec
from toolchain.containers.planner import ContainerRunPlanner
from toolchain.errors import BackendUnavailableError, ContainerCreateError, ContainerPlanError
from toolchain.providers.docker.container_backend import DockerContainerBackend
from toolchain.providers.docker.runner import CommandResult


def make_plan(tmp_path, host_environment=None, **kwargs):
    return ContainerRunPlanner().plan(
        "dev",
        ContainerSpec(image="ubuntu:24.04", **kwargs),
        tmp_path / "toolchain.yaml",
        host_environment or {},
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


def test_defaults_create_immutable_detached_plan(tmp_path):
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


def test_flat_mount_syntax_normalizes_bind_volume_and_read_only(tmp_path):
    plan = make_plan(
        tmp_path,
        mounts=[
            "../:/workspace",
            "/dev:/dev",
            "cache:/cache:ro",
        ],
    )
    assert [(m.type, m.source, m.target, m.read_only) for m in plan.mounts] == [
        ("bind", str(tmp_path.parent), "/workspace", False),
        ("bind", "/dev", "/dev", False),
        ("volume", "cache", "/cache", True),
    ]
    command = DockerContainerBackend().command(plan)
    assert "--mount=type=volume,source=cache,target=/cache,readonly" in command


@pytest.mark.parametrize(
    "mount",
    [
        "/dev",
        ":/dev",
        "/dev:relative",
        "/dev:/dev:cached",
        "/a:/same",
        "/a,b:/target",
        "bad name:/target",
    ],
)
def test_invalid_mounts_fail_before_docker(tmp_path, mount):
    mounts = [mount]
    if mount == "/a:/same":
        mounts.append("/b:/same")
    with pytest.raises(ContainerPlanError):
        make_plan(tmp_path, mounts=mounts)


def test_robot_options_and_host_environment(tmp_path):
    plan = make_plan(
        tmp_path,
        host_environment={"DISPLAY": ":0", "USER": "developer"},
        name="robot-dev",
        privileged=True,
        devices=["/dev/dri"],
        group_add=["video"],
        network="host",
        ipc="host",
        workdir="/workspace",
        mounts=["/dev:/dev"],
        environment={"DISPLAY": {"env": "DISPLAY"}, "USER": {"env": "USER"}},
        command=["/bin/bash"],
    )
    command = DockerContainerBackend().command(plan)
    assert "--privileged" in command and "--device=/dev/dri" in command
    assert "--group-add=video" in command
    assert "--network=host" in command and "--ipc=host" in command
    assert "--env=DISPLAY=:0" in command and command[-2:] == ("ubuntu:24.04", "/bin/bash")


def test_missing_host_environment_is_actionable(tmp_path):
    with pytest.raises(ContainerPlanError, match="missing host environment"):
        make_plan(tmp_path, environment={"DISPLAY": {"env": "MISSING"}})


def test_backend_never_invokes_a_shell_and_redacts_environment(tmp_path):
    plan = make_plan(tmp_path, environment={"TOKEN": "sensitive"}, command=["echo", "$USER"])
    runner = FakeRunner(CommandResult(125, stderr="bad sensitive"))
    with pytest.raises(ContainerCreateError) as error:
        DockerContainerBackend(runner).create(plan)
    assert "sensitive" not in str(error.value)
    assert len(runner.calls) == 1
    assert runner.calls[0][0][-2:] == ("echo", "$USER")


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
    path.write_text("""version: 2
metadata: {name: container-test}
sources: {containers: config/containers.yaml}
""")
    source = tmp_path / "config/containers.yaml"
    source.parent.mkdir()
    source.write_text("""development:
    name:
      default: robot-dev
      prompt: {mode: input, message: Container name}
    image: ubuntu:24.04
    privileged:
      default: false
      prompt: {mode: confirm, message: "Privileged?"}
    mounts:
      default: ["../:/workspace"]
      prompt: {mode: input, repeat: true, message: Mount}
    environment: {TOKEN: never-print-this}
""")
    return path


def test_use_case_resolves_selected_inline_values(tmp_path):
    config = write_config(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("""containers:
  development:
    privileged: true
""")
    use_case = CreateContainerUseCase(FakeBackend())
    plan = use_case.plan(
        "development",
        ResolutionRequest(
            config,
            values_path=values,
            overrides={"containers.development.name": "chosen"},
            interactive=False,
        ),
    )
    assert plan.container_name == "chosen" and plan.privileged is True


def test_cli_uses_default_project_config_and_path_overrides(tmp_path, monkeypatch, capsys):
    write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr("toolchain.cli.commands.containers.DockerContainerBackend", lambda: backend)
    command = [
        "container",
        "create",
        "development",
        "--non-interactive",
        "--set",
        "containers.development.name=chosen",
        "--set",
        'containers.development.mounts=["./:/workspace"]',
    ]
    assert run([*command, "--dry-run"]) == 0
    assert "Container: chosen" in capsys.readouterr().out
    assert run(command) == 0
    assert backend.plans[0].container_name == "chosen"


@pytest.mark.parametrize("answer,expected", [("y", 1), ("n", 0)])
def test_menu_resolves_prompts_before_confirmation(tmp_path, answer, expected):
    config = write_config(tmp_path)
    backend = FakeBackend()
    output = io.StringIO()
    # Create container, select development, accept name/default mounts,
    # answer privileged, then confirm or cancel. The process exits after the action.
    inputs = io.StringIO(f"2\n1\n\n{answer}\n\n{answer}\n")
    app = MenuApp(MenuIO(inputs, output), container_backend_factory=lambda: backend)
    assert app.run(config) == 0
    assert len(backend.plans) == expected
    assert "never-print-this" not in output.getvalue()
