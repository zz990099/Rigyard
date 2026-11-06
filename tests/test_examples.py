import io
import shutil
from pathlib import Path

import pytest

from rigyard.application.builds import BuildProjectUseCase
from rigyard.application.containers import CreateContainerUseCase
from rigyard.application.images import BuildImageUseCase
from rigyard.application.parameters import ValidateConfigUseCase
from rigyard.application.requests import BuildImageRequest, ResolutionRequest
from rigyard.application.scenarios import PlanScenarioUseCase
from rigyard.cli.main import run
from rigyard.execution.runner import SubprocessRunner
from rigyard.providers.docker import DockerExecBuildBackend, DockerImageBackend
from rigyard.providers.docker.container_backend import DockerContainerBackend

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["minimal", "robot-development"])
def test_repository_example_is_valid(name: str):
    config = ValidateConfigUseCase().execute(ROOT / "examples" / name / "rigyard.yaml")

    assert config.metadata.name


def test_robot_example_loads_logo_and_workflow_sources():
    config = ValidateConfigUseCase().execute(
        ROOT / "examples" / "robot-development" / "rigyard.yaml"
    )

    assert config.workspace.command_alias == "robot"
    assert "ROBOT DEVELOPMENT" in (config.branding.logo or "")
    assert all(
        config.source_files[kind] for kind in ("images", "containers", "builds", "scenarios")
    )


@pytest.fixture
def robot_sandbox(tmp_path, monkeypatch):
    project = tmp_path / "robot workspace"
    shutil.copytree(ROOT / "examples" / "robot-development", project)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("USER", "sandbox")
    monkeypatch.delenv("DISPLAY", raising=False)

    def forbid_execution(*args, **kwargs):
        pytest.fail("example validation and planning must not execute external commands")

    monkeypatch.setattr(SubprocessRunner, "run", forbid_execution)
    return project / "rigyard.yaml"


def test_robot_workflow_paths_and_targets_agree_outside_project_directory(robot_sandbox):
    request = ResolutionRequest(robot_sandbox, interactive=False)
    image = BuildImageUseCase(DockerImageBackend()).plan(
        BuildImageRequest(robot_sandbox, "development", interactive=False)
    )
    container = CreateContainerUseCase(DockerContainerBackend()).plan("development", request)
    build = BuildProjectUseCase(DockerExecBuildBackend()).plan("development", request)
    scene = PlanScenarioUseCase().plan("nav2-tb3", None, request)

    assert image.steps[0].base_image == "ubuntu:24.04"
    assert image.steps[1].base_image == image.steps[0].output_tag
    assert all(step.context == robot_sandbox.parent for step in image.steps)
    assert container.image == image.final_tag
    assert container.container_name == build.container == scene.instances[0].container
    workspace = next(mount for mount in container.mounts if mount.target == str(build.workdir))
    assert Path(workspace.source) == robot_sandbox.parent
    host_script = Path(workspace.source) / build.script.relative_to(workspace.target)
    assert host_script.is_file()
    group = scene.instances[0].groups[0]
    assert group.setup == build.setup == ("/opt/ros/jazzy/setup.bash",)
    assert group.workdir == str(build.workdir)
    assert group.command is not None
    assert group.command[:4] == ("ros2", "launch", "nav2_bringup", "tb3_simulation_launch.py")
    assert dict(container.environment)["DISPLAY"] == ""


@pytest.mark.parametrize(
    "command",
    [
        ["validate"],
        ["resolve", "--non-interactive"],
        ["container", "create", "development", "--dry-run", "--non-interactive"],
        ["build", "development", "--dry-run", "--non-interactive"],
        ["scene", "start", "nav2-tb3", "--dry-run", "--non-interactive"],
    ],
)
def test_robot_documented_previews_do_not_need_docker(robot_sandbox, command):
    output = io.StringIO()
    errors = io.StringIO()

    status = run(
        ["--config", str(robot_sandbox), *command],
        stdout=output,
        stderr=errors,
    )

    assert status == 0, errors.getvalue()
    assert output.getvalue()
