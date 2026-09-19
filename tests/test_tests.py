import io
import subprocess
from pathlib import Path

import pytest

from rigyard.application.requests import ResolutionRequest
from rigyard.application.tests import ExecuteTestUseCase
from rigyard.cli.main import run
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.config.loader import load_config
from rigyard.errors import (
    BackendUnavailableError,
    SchemaValidationError,
)
from rigyard.errors import TestExecutionError as CommandFailure
from rigyard.execution import CommandResult as ProcessResult
from rigyard.providers.docker import DockerExecTestBackend
from rigyard.tests.models import TestPlan as CommandPlan
from rigyard.tests.models import TestResult as ActionResult


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(tmp_path: Path, tests: str) -> Path:
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: test-project}
sources: {tests: config/tests.yaml}
""",
    )
    write(tmp_path / "config/tests.yaml", tests)
    return config


class RecordingBackend:
    def __init__(self) -> None:
        self.plans: list[CommandPlan] = []

    def execute(self, plan: CommandPlan) -> ActionResult:
        self.plans.append(plan)
        return ActionResult(plan.test_name, plan.action, plan.command)


def definition() -> str:
    return """unit:
  description: Unit tests
  container: dev
  workdir: /workspace
  user: root
  setup: [/opt/ros/humble/setup.bash, install/setup.bash]
  environment: {TEST_JOBS: "4"}
  run:
    script: /workspace/scripts/run-tests.sh
    interpreter: [/bin/bash, -euo, pipefail]
    timeout_seconds: 1800
  report:
    script: /workspace/scripts/show-results.sh
    interpreter: [/bin/bash, -eu]
    timeout_seconds: 60
"""


def test_load_test_only_project(tmp_path: Path):
    config = project(tmp_path, definition())

    loaded = load_config(config)

    assert loaded.sources.tests == Path("config/tests.yaml")
    assert loaded.tests["unit"].description == "Unit tests"
    assert loaded.tests["unit"].run.script == Path("/workspace/scripts/run-tests.sh")
    assert loaded.images == {}
    assert loaded.builds == {}


@pytest.mark.parametrize(
    ("action", "script", "interpreter", "timeout"),
    [
        ("run", "/workspace/scripts/run-tests.sh", ("/bin/bash", "-euo", "pipefail"), 1800),
        ("report", "/workspace/scripts/show-results.sh", ("/bin/bash", "-eu"), 60),
    ],
)
def test_plan_selects_user_defined_action(tmp_path: Path, action, script, interpreter, timeout):
    config = project(tmp_path, definition())

    plan = ExecuteTestUseCase(RecordingBackend()).plan(
        "unit", action, ResolutionRequest(config, interactive=False)
    )

    assert plan.action == action
    assert plan.script == Path(script)
    assert plan.timeout_seconds == timeout
    assert plan.command[:6] == (
        "docker",
        "exec",
        "--user=root",
        "--workdir=/workspace",
        "--env=TEST_JOBS=4",
        "dev",
    )
    program = (
        ". /opt/ros/humble/setup.bash && . install/setup.bash && "
        f"exec {' '.join((*interpreter, script))}"
    )
    assert plan.command[6:] == (*interpreter, "-c", program)


def test_runtime_values_apply_to_both_commands(tmp_path: Path):
    config = project(
        tmp_path,
        """unit:
  container: {default: dev, prompt: {mode: input, message: Container}}
  environment:
    TEST_JOBS: {default: "4", prompt: {mode: input, message: Jobs}}
  run: {script: /workspace/run.sh}
  report: {script: /workspace/report.sh}
""",
    )

    plan = ExecuteTestUseCase(RecordingBackend()).plan(
        "unit",
        "report",
        ResolutionRequest(
            config,
            overrides={
                "tests.unit.container": "ci",
                "tests.unit.environment.TEST_JOBS": "8",
            },
            interactive=False,
        ),
    )

    assert plan.container == "ci"
    assert plan.environment == (("TEST_JOBS", "8"),)
    assert "--env=TEST_JOBS=8" in plan.command


def test_both_actions_are_required(tmp_path: Path):
    config = project(
        tmp_path,
        "unit: {container: dev, run: {script: /workspace/run.sh}}\n",
    )

    with pytest.raises(SchemaValidationError, match="report"):
        load_config(config)


class FakeRunner:
    def __init__(self, outcomes: list[ProcessResult | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def sample_plan(action="report") -> CommandPlan:
    return CommandPlan(
        test_name="unit",
        action=action,
        container="dev",
        script=Path(f"/workspace/{action}.sh"),
        command=("docker", "exec", "dev", "/bin/sh", "-eu", f"/workspace/{action}.sh"),
        workdir=None,
        user=None,
        setup=(),
        environment=(),
        environment_overrides=(),
        timeout_seconds=30,
    )


def test_backend_streams_user_output_without_capture():
    runner = FakeRunner([ProcessResult(0, "true\n"), ProcessResult(0)])
    plan = sample_plan()

    result = DockerExecTestBackend(runner).execute(plan)

    assert result.action == "report"
    assert runner.calls[1] == (
        plan.command,
        {"capture": False, "timeout_seconds": 30},
    )


def test_backend_reports_process_and_infrastructure_errors():
    plan = sample_plan("run")
    with pytest.raises(CommandFailure, match="exit code 17"):
        DockerExecTestBackend(
            FakeRunner([ProcessResult(0, "true\n"), ProcessResult(17)])
        ).execute(plan)
    with pytest.raises(CommandFailure, match="timed out after 30 seconds"):
        DockerExecTestBackend(
            FakeRunner(
                [ProcessResult(0, "true\n"), subprocess.TimeoutExpired(plan.command, 30)]
            )
        ).execute(plan)
    with pytest.raises(BackendUnavailableError, match="cannot execute Docker"):
        DockerExecTestBackend(FakeRunner([FileNotFoundError("missing")])).execute(plan)


def test_cli_dry_run_does_not_execute(tmp_path: Path, monkeypatch, capsys):
    config = project(tmp_path, definition())

    class ForbiddenBackend:
        def execute(self, plan):
            raise AssertionError("dry-run must not execute")

    monkeypatch.setattr("rigyard.cli.commands.tests.DockerExecTestBackend", ForbiddenBackend)
    assert run(["--config", str(config), "test", "report", "unit", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Test: unit" in output
    assert "Action: report" in output
    assert "/workspace/scripts/show-results.sh" in output


@pytest.mark.parametrize("action", ["run", "report"])
def test_cli_executes_selected_command(tmp_path: Path, monkeypatch, capsys, action):
    config = project(tmp_path, definition())
    backend = RecordingBackend()
    monkeypatch.setattr(
        "rigyard.cli.commands.tests.DockerExecTestBackend", lambda: backend
    )

    assert run(["--config", str(config), "test", action, "unit"]) == 0
    assert [plan.action for plan in backend.plans] == [action]
    assert f"{action} command completed" in capsys.readouterr().out


def test_menu_runs_test_command_once_and_exits(tmp_path: Path):
    config = project(tmp_path, definition())
    backend = RecordingBackend()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("5\n1\n1\ny\n"), output),
        test_backend_factory=lambda: backend,
    )

    assert app.run(config) == 0
    assert [plan.action for plan in backend.plans] == ["run"]
    rendered = output.getvalue()
    assert rendered.count("Configuration:") == 1
    assert "Test…" in rendered
    assert "run command completed" in rendered
