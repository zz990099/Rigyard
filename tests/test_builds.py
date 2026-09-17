import io
import subprocess
from pathlib import Path

import pytest

from toolchain.application.builds import BuildProjectUseCase
from toolchain.application.requests import ResolutionRequest
from toolchain.builds.models import BuildPlan, BuildResult
from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.config.loader import load_config
from toolchain.errors import BackendUnavailableError, BuildExecutionError, BuildPlanError
from toolchain.execution import CommandResult
from toolchain.providers.host import HostBuildBackend


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(tmp_path: Path, builds: str) -> Path:
    config = write(
        tmp_path / "toolchain.yaml",
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
  script: scripts/build.sh
""",
    )

    loaded = load_config(config)

    assert loaded.sources.builds == Path("config/builds.yaml")
    assert loaded.builds["native"].description == "Native build"
    assert loaded.images == {}
    assert loaded.containers == {}


def test_plan_resolves_only_selected_build_and_relative_paths(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  script: scripts/native.sh
  interpreter: [/bin/bash, -eu]
  workdir: workspace
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Build type
        options: [Debug, Release]
cross:
  script:
    prompt: {mode: input, message: Cross build script}
""",
    )
    script = write(tmp_path / "scripts/native.sh", "echo build\n")
    (tmp_path / "workspace").mkdir()
    backend = RecordingBackend()

    plan = BuildProjectUseCase(backend).plan(
        "native",
        ResolutionRequest(config, interactive=False),
        environment={"PATH": "/usr/bin"},
    )

    assert plan.script == script.resolve()
    assert plan.command == ("/bin/bash", "-eu", str(script.resolve()))
    assert plan.workdir == (tmp_path / "workspace").resolve()
    assert dict(plan.environment) == {"PATH": "/usr/bin", "BUILD_TYPE": "Release"}
    assert plan.environment_overrides == ("BUILD_TYPE",)


def test_values_for_other_builds_are_allowed_and_filtered(tmp_path: Path):
    config = project(
        tmp_path,
        """native:
  script: scripts/native.sh
  environment:
    MODE: {default: Release, prompt: {mode: input, message: Mode}}
cross:
  script: scripts/cross.sh
  environment:
    SYSROOT: {prompt: {mode: input, message: Sysroot}}
""",
    )
    write(tmp_path / "scripts/native.sh", "echo native\n")
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


def test_invalid_script_and_workdir_are_rejected(tmp_path: Path):
    config = project(tmp_path, "native: {script: missing.sh}\n")
    use_case = BuildProjectUseCase(RecordingBackend())

    with pytest.raises(BuildPlanError, match="script is not a file"):
        use_case.plan("native", ResolutionRequest(config, interactive=False), environment={})

    write(tmp_path / "build.sh", "echo build\n")
    write(tmp_path / "not-a-directory", "file\n")
    config = project(
        tmp_path,
        "native: {script: build.sh, workdir: not-a-directory}\n",
    )
    with pytest.raises(BuildPlanError, match="workdir is not a directory"):
        use_case.plan("native", ResolutionRequest(config, interactive=False), environment={})


class FakeRunner:
    def __init__(self, outcome: CommandResult | Exception) -> None:
        self.outcome = outcome
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def sample_plan(tmp_path: Path) -> BuildPlan:
    script = write(tmp_path / "build.sh", "echo build\n")
    return BuildPlan(
        build_name="native",
        script=script,
        command=("/bin/sh", "-eu", str(script)),
        workdir=tmp_path,
        environment=(("BUILD_TYPE", "Release"),),
        environment_overrides=("BUILD_TYPE",),
        timeout_seconds=30,
    )


def test_host_backend_executes_argv_with_workdir_and_environment(tmp_path: Path):
    runner = FakeRunner(CommandResult(0))
    plan = sample_plan(tmp_path)

    result = HostBuildBackend(runner).execute(plan)

    assert result.build_name == "native"
    command, kwargs = runner.calls[0]
    assert command == plan.command
    assert kwargs["cwd"] == tmp_path
    assert kwargs["environment"] == {"BUILD_TYPE": "Release"}
    assert kwargs["timeout_seconds"] == 30
    assert "shell" not in kwargs
    assert kwargs.get("capture", False) is False


def test_host_backend_reports_exit_timeout_and_missing_interpreter(tmp_path: Path):
    plan = sample_plan(tmp_path)
    with pytest.raises(BuildExecutionError, match="exit code 17"):
        HostBuildBackend(FakeRunner(CommandResult(17))).execute(plan)
    with pytest.raises(BuildExecutionError, match="timed out after 30 seconds"):
        HostBuildBackend(FakeRunner(subprocess.TimeoutExpired(plan.command, 30))).execute(plan)
    with pytest.raises(BackendUnavailableError, match="cannot execute build"):
        HostBuildBackend(FakeRunner(FileNotFoundError("missing"))).execute(plan)


def test_cli_dry_run_resolves_build_without_executing(tmp_path: Path, monkeypatch, capsys):
    config = project(
        tmp_path,
        """native:
  script: scripts/build.sh
  environment:
    BUILD_TYPE: Release
""",
    )
    write(tmp_path / "scripts/build.sh", "echo build\n")

    class ForbiddenBackend:
        def execute(self, plan):
            raise AssertionError("dry-run must not execute")

    monkeypatch.setattr("toolchain.cli.commands.builds.HostBuildBackend", ForbiddenBackend)
    assert run(["--config", str(config), "build", "native", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Build: native" in output
    assert "Command: /bin/sh -eu" in output
    assert "Environment overrides: BUILD_TYPE" in output


def test_cli_build_executes_once_and_returns_backend_error(tmp_path: Path, monkeypatch, capsys):
    config = project(tmp_path, "native: {script: build.sh}\n")
    write(tmp_path / "build.sh", "echo build\n")
    backend = RecordingBackend()
    monkeypatch.setattr("toolchain.cli.commands.builds.HostBuildBackend", lambda: backend)

    assert run(["--config", str(config), "build", "native"]) == 0
    assert len(backend.plans) == 1
    assert "completed" in capsys.readouterr().out

    class FailingBackend:
        def execute(self, plan):
            raise BuildExecutionError("failed")

    monkeypatch.setattr("toolchain.cli.commands.builds.HostBuildBackend", FailingBackend)
    assert run(["--config", str(config), "build", "native"]) == 4
    assert "Error: failed" in capsys.readouterr().err


def test_menu_build_executes_once_and_exits(tmp_path: Path):
    config = project(tmp_path, "native: {description: Native, script: build.sh}\n")
    write(tmp_path / "build.sh", "echo build\n")
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
