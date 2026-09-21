import io
import subprocess
from pathlib import Path

import pytest

from rigyard.application.builds import BuildProjectUseCase
from rigyard.application.requests import ResolutionRequest
from rigyard.builds.models import BuildPlan, BuildResult
from rigyard.cli.build_output import describe_build
from rigyard.cli.main import run
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.cli.style import Style
from rigyard.config.loader import load_config
from rigyard.errors import (
    BackendUnavailableError,
    BuildExecutionError,
    SchemaValidationError,
)
from rigyard.execution import CommandResult
from rigyard.parameters.sources import DynamicOption
from rigyard.providers.docker import DockerExecBuildBackend


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(tmp_path: Path, builds: str) -> Path:
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: build-test}
sources: {builds: config/builds.yaml}
""",
    )
    write(tmp_path / "config/builds.yaml", builds)
    return config


class RecordingBackend:
    def __init__(self) -> None:
        self.plans: list[BuildPlan] = []

    def execute(self, plan: BuildPlan) -> BuildResult:
        self.plans.append(plan)
        return BuildResult(plan.build_name, plan.command)


def test_load_build_only_project(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  description: Native build
  container: dev
  script: /workspace/build.sh
""",
    )

    loaded = load_config(config)

    assert loaded.sources.builds == Path("config/builds.yaml")
    assert loaded.builds["native"].description == "Native build"
    assert loaded.builds["native"].container == "dev"
    assert loaded.builds["native"].script == Path("/workspace/build.sh")
    assert loaded.builds["native"].start_container is True
    assert loaded.images == {}
    assert loaded.containers == {}


def test_plan_uses_container_paths_and_selected_build(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container: dev
  script: /workspace/scripts/native.sh
  interpreter: [/bin/bash, -eu]
  workdir: /workspace
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Build type
        options: [Debug, Release]
cross:
  container: cross
  script:
    prompt: {mode: input, message: Cross build script}
""",
    )

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native",
        ResolutionRequest(config, interactive=False),
        environment={"PATH": "/usr/bin"},
    )

    assert plan.container == "dev"
    assert plan.start_container is True
    assert plan.script == Path("/workspace/scripts/native.sh")
    assert plan.workdir == Path("/workspace")
    assert plan.command == (
        "docker",
        "exec",
        "--workdir=/workspace",
        "--env=BUILD_TYPE=Release",
        "dev",
        "/bin/bash",
        "-eu",
        "/workspace/scripts/native.sh",
    )
    assert plan.environment == (("BUILD_TYPE", "Release"),)
    assert plan.environment_overrides == ("BUILD_TYPE",)


def test_interactive_prompt_shows_rendered_default(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container:
    default: dev_${env:USER}
    prompt: {mode: input, message: Choose the container}
  script: /workspace/build.sh
""",
    )
    seen: list[str] = []

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native",
        ResolutionRequest(
            config,
            interactive=True,
            input_fn=lambda text: seen.append(text) or "",
        ),
        environment={"USER": "root"},
    )

    assert seen == ["Choose the container [dev_root]: "]
    assert plan.container == "dev_root"


def test_interactive_container_prompt_lists_dynamic_candidates(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container:
    default: dev_${env:USER}
    prompt:
      mode: select
      message: Choose the container
      source: {provider: containers, filter: "^dev_"}
  script: /workspace/build.sh
""",
    )
    seen: list[str] = []
    sources = {
        "containers": lambda source: (
            DynamicOption("dev_root", "running, nhybot:base"),
            DynamicOption("dev_root_sim", "exited, nhybot:base"),
        )
    }

    plan = BuildProjectUseCase(RecordingBackend(), sources=sources).plan(
        "native",
        ResolutionRequest(
            config,
            interactive=True,
            input_fn=lambda text: seen.append(text) or "1",
        ),
        environment={"USER": "root"},
    )

    assert seen == [
        "  1) dev_root      running, nhybot:base\n"
        "  2) dev_root_sim  exited, nhybot:base\n"
        "Choose the container [dev_root]: "
    ]
    assert plan.container == "dev_root"


def test_values_for_other_builds_are_allowed_and_filtered(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container: dev
  script: /workspace/native.sh
  environment:
    MODE: {default: Release, prompt: {mode: input, message: Mode}}
cross:
  container: cross
  script: /workspace/cross.sh
  environment:
    SYSROOT: {prompt: {mode: input, message: Sysroot}}
""",
    )
    values = write(
        tmp_path / "values.yaml",
        """builds:
  native: {environment: {MODE: Debug}}
  cross: {environment: {SYSROOT: /opt/sysroot}}
""",
    )

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native",
        ResolutionRequest(config, values_path=values, interactive=False),
        environment={},
    )

    assert dict(plan.environment) == {"MODE": "Debug"}


def test_build_requires_container(tmp_path: Path):
    config = project(tmp_path, "native: {script: /workspace/build.sh}\n")

    with pytest.raises(SchemaValidationError, match="container"):
        load_config(config)


def test_build_can_disable_automatic_container_start(tmp_path: Path):
    config = project(
        tmp_path,
        "native: {container: dev, start_container: false, script: /workspace/build.sh}\n",
    )

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native", ResolutionRequest(config, interactive=False)
    )

    assert plan.start_container is False


def test_setup_wraps_the_container_command(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container: dev
  script: /workspace/build.sh
  interpreter: [/bin/bash, -euo, pipefail]
  setup: [/opt/ros/humble/setup.bash, install/setup.bash]
""",
    )

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native",
        ResolutionRequest(config, interactive=False),
    )

    program = (
        ". /opt/ros/humble/setup.bash && . install/setup.bash && "
        "exec /bin/bash -euo pipefail /workspace/build.sh"
    )
    assert plan.command == (
        "docker",
        "exec",
        "dev",
        "/bin/bash",
        "-euo",
        "pipefail",
        "-c",
        program,
    )


def test_user_is_passed_to_docker_exec(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  container: dev
  user: root
  script: /workspace/build.sh
""",
    )

    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native",
        ResolutionRequest(config, interactive=False),
    )

    assert plan.command[:4] == ("docker", "exec", "--user=root", "dev")


class FakeRunner:
    def __init__(self, outcomes: list[CommandResult | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def sample_plan() -> BuildPlan:
    return BuildPlan(
        build_name="native",
        container="dev",
        script=Path("/workspace/build.sh"),
        command=(
            "docker",
            "exec",
            "--workdir=/workspace",
            "--env=BUILD_TYPE=Release",
            "dev",
            "/bin/bash",
            "-eu",
            "/workspace/build.sh",
        ),
        workdir=Path("/workspace"),
        user=None,
        setup=(),
        environment=(("BUILD_TYPE", "Release"),),
        environment_overrides=("BUILD_TYPE",),
        timeout_seconds=30,
        tty="auto",
    )


def test_tty_policy_controls_docker_exec(tmp_path: Path):
    config = project(
        tmp_path,
        "native: {container: dev, script: /workspace/build.sh, tty: always}\n",
    )
    plan = BuildProjectUseCase(RecordingBackend()).plan(
        "native", ResolutionRequest(config, interactive=False)
    )

    assert plan.tty == "always"
    assert plan.command[:3] == ("docker", "exec", "--tty")


def test_auto_tty_is_allocated_only_for_terminal_output():
    plan = sample_plan()
    terminal_runner = FakeRunner([CommandResult(0, "true\n"), CommandResult(0)])
    terminal_backend = DockerExecBuildBackend(terminal_runner)
    terminal_backend.executor.is_terminal = lambda: True
    terminal_backend.execute(plan)
    assert terminal_runner.calls[1][0][:3] == ("docker", "exec", "--tty")

    redirected_runner = FakeRunner([CommandResult(0, "true\n"), CommandResult(0)])
    redirected_backend = DockerExecBuildBackend(redirected_runner)
    redirected_backend.executor.is_terminal = lambda: False
    redirected_backend.execute(plan)
    assert redirected_runner.calls[1][0] == plan.command


def test_plan_lines_keep_their_text_and_carry_roles():
    lines = describe_build(sample_plan())

    assert [str(item) for item in lines] == [
        "Build: native",
        "Container: dev",
        "Start stopped container: true",
        "Working directory: /workspace",
        "Command: docker exec --workdir=/workspace --env=BUILD_TYPE=Release dev "
        "/bin/bash -eu /workspace/build.sh",
        "Environment overrides: BUILD_TYPE",
        "Timeout: 30 seconds",
    ]

    style = Style(enabled=True)
    assert lines[0].render(style) == "\x1b[2mBuild\x1b[0m: \x1b[1mnative\x1b[0m"
    assert lines[5].render(style) == (
        "\x1b[2mEnvironment overrides\x1b[0m: \x1b[2mBUILD_TYPE\x1b[0m"
    )


def test_docker_exec_backend_checks_container_and_executes():
    runner = FakeRunner([CommandResult(0, "true\n"), CommandResult(0)])
    plan = sample_plan()

    result = DockerExecBuildBackend(runner).execute(plan)

    assert result.build_name == "native"
    inspect_command, inspect_kwargs = runner.calls[0]
    assert inspect_command == ("docker", "inspect", "--format={{.State.Running}}", "dev")
    assert inspect_kwargs["capture"] is True
    exec_command, exec_kwargs = runner.calls[1]
    assert exec_command == plan.command
    assert exec_kwargs["timeout_seconds"] == 30
    assert exec_kwargs.get("capture", False) is False
    assert "environment" not in exec_kwargs


def test_docker_exec_backend_rejects_missing_container():
    plan = sample_plan()
    with pytest.raises(BuildExecutionError, match="does not exist"):
        DockerExecBuildBackend(
            FakeRunner([CommandResult(1, stderr="No such object\n")])
        ).execute(plan)


def test_docker_exec_backend_starts_stopped_container_before_exec():
    plan = sample_plan()
    runner = FakeRunner(
        [
            CommandResult(0, "false\n"),
            CommandResult(0, "dev\n"),
            CommandResult(0, "true\n"),
            CommandResult(0),
        ]
    )

    DockerExecBuildBackend(runner).execute(plan)

    assert [call[0] for call in runner.calls] == [
        ("docker", "inspect", "--format={{.State.Running}}", "dev"),
        ("docker", "start", "dev"),
        ("docker", "inspect", "--format={{.State.Running}}", "dev"),
        plan.command,
    ]


def test_docker_exec_backend_can_require_an_already_running_container():
    plan = BuildPlan(**{**sample_plan().__dict__, "start_container": False})
    with pytest.raises(BuildExecutionError, match="is not running"):
        DockerExecBuildBackend(FakeRunner([CommandResult(0, "false\n")])).execute(plan)


def test_docker_exec_backend_reports_start_failure_and_immediate_exit():
    plan = sample_plan()
    with pytest.raises(BuildExecutionError, match="cannot start container.*permission denied"):
        DockerExecBuildBackend(
            FakeRunner(
                [
                    CommandResult(0, "false\n"),
                    CommandResult(1, stderr="permission denied\n"),
                ]
            )
        ).execute(plan)
    with pytest.raises(BuildExecutionError, match="did not remain running"):
        DockerExecBuildBackend(
            FakeRunner(
                [
                    CommandResult(0, "false\n"),
                    CommandResult(0, "dev\n"),
                    CommandResult(0, "false\n"),
                ]
            )
        ).execute(plan)


def test_docker_exec_backend_reports_exit_timeout_and_docker_errors():
    plan = sample_plan()
    with pytest.raises(BuildExecutionError, match="exit code 17"):
        DockerExecBuildBackend(
            FakeRunner([CommandResult(0, "true\n"), CommandResult(17)])
        ).execute(plan)
    with pytest.raises(BuildExecutionError, match="timed out after 30 seconds"):
        DockerExecBuildBackend(
            FakeRunner(
                [
                    CommandResult(0, "true\n"),
                    subprocess.TimeoutExpired(plan.command, 30),
                ]
            )
        ).execute(plan)
    with pytest.raises(BackendUnavailableError, match="cannot execute Docker"):
        DockerExecBuildBackend(FakeRunner([FileNotFoundError("missing")])).execute(plan)
    with pytest.raises(BackendUnavailableError, match="cannot execute build"):
        DockerExecBuildBackend(
            FakeRunner([CommandResult(0, "true\n"), FileNotFoundError("missing")])
        ).execute(plan)


def test_cli_dry_run_resolves_build_without_executing(tmp_path: Path, monkeypatch, capsys):
    config = project(
        tmp_path,
        """native:
  container: dev
  script: /workspace/build.sh
  environment:
    BUILD_TYPE: Release
""",
    )

    class ForbiddenBackend:
        def execute(self, plan):
            raise AssertionError("dry-run must not execute")

    monkeypatch.setattr("rigyard.cli.commands.builds.DockerExecBuildBackend", ForbiddenBackend)
    assert run(["--config", str(config), "build", "native", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Build: native" in output
    assert "Container: dev" in output
    assert "Command: docker exec" in output
    assert "Environment overrides: BUILD_TYPE" in output


def test_cli_build_executes_once_and_returns_backend_error(tmp_path: Path, monkeypatch, capsys):
    config = project(tmp_path, "native: {container: dev, script: /workspace/build.sh}\n")
    backend = RecordingBackend()
    monkeypatch.setattr("rigyard.cli.commands.builds.DockerExecBuildBackend", lambda: backend)

    assert run(["--config", str(config), "build", "native"]) == 0
    assert len(backend.plans) == 1
    assert "completed" in capsys.readouterr().out

    class FailingBackend:
        def execute(self, plan):
            raise BuildExecutionError("failed")

    monkeypatch.setattr("rigyard.cli.commands.builds.DockerExecBuildBackend", FailingBackend)
    assert run(["--config", str(config), "build", "native"]) == 4
    assert "Error: failed" in capsys.readouterr().err


def test_menu_build_executes_once_and_exits(tmp_path: Path):
    config = project(
        tmp_path,
        "native: {description: Native, container: dev, script: /workspace/build.sh}\n",
    )
    backend = RecordingBackend()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("3\n1\ny\n"), output),
        build_backend_factory=lambda: backend,
    )

    assert app.run(config) == 0
    assert len(backend.plans) == 1
    rendered = output.getvalue()
    assert rendered.count("Configuration:") == 1
    assert "Build project" in rendered
    assert "Build 'native' completed" in rendered
