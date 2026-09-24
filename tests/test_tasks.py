import io
import subprocess
from pathlib import Path

import pytest

from rigyard.application.requests import ResolutionRequest
from rigyard.application.tasks import ExecuteTaskUseCase
from rigyard.cli.main import run
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.config.loader import load_config
from rigyard.errors import BackendUnavailableError, SchemaValidationError
from rigyard.errors import TaskExecutionError as CommandFailure
from rigyard.execution import CommandResult as ProcessResult
from rigyard.providers.docker import DockerExecTaskBackend
from rigyard.tasks.models import TaskPlan as CommandPlan
from rigyard.tasks.models import TaskResult as ActionResult


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(tmp_path: Path, tasks: str) -> Path:
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: task-project}
sources: {tasks: config/tasks.yaml}
""",
    )
    write(tmp_path / "config/tasks.yaml", tasks)
    return config


class RecordingBackend:
    def __init__(self) -> None:
        self.plans: list[CommandPlan] = []

    def execute(self, plan: CommandPlan) -> ActionResult:
        self.plans.append(plan)
        return ActionResult(plan.task_name, plan.command)


def definition(*, confirm: bool = True) -> str:
    confirm_text = str(confirm).lower()
    return f"""clean:
  description: Clean build artifacts
  container: dev
  script: /workspace/scripts/clean.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: /workspace
  user: root
  setup: [/opt/ros/humble/setup.bash, install/setup.bash]
  environment: {{CLEAN_INSTALL: "false"}}
  timeout_seconds: 300
  menu:
    enabled: true
    label: Clean workspace
    confirm: {confirm_text}
"""


def test_load_task_only_project(tmp_path: Path):
    config = project(tmp_path, definition())

    loaded = load_config(config)

    assert loaded.sources.tasks == Path("config/tasks.yaml")
    assert loaded.tasks["clean"].description == "Clean build artifacts"
    assert loaded.tasks["clean"].menu.label == "Clean workspace"
    assert loaded.tasks["clean"].start_container is True
    assert loaded.images == {}
    assert loaded.tests == {}


def test_plan_uses_container_paths_setup_and_environment(tmp_path: Path):
    config = project(tmp_path, definition())

    plan = ExecuteTaskUseCase(RecordingBackend()).plan(
        "clean", ResolutionRequest(config, interactive=False)
    )

    assert plan.container == "dev"
    assert plan.start_container is True
    assert plan.script == Path("/workspace/scripts/clean.sh")
    assert plan.timeout_seconds == 300
    assert plan.command[:6] == (
        "docker",
        "exec",
        "--user=root",
        "--workdir=/workspace",
        "--env=CLEAN_INSTALL=false",
        "dev",
    )
    assert plan.command[6:] == (
        "/bin/bash",
        "-euo",
        "pipefail",
        "-c",
        ". /opt/ros/humble/setup.bash && . install/setup.bash && "
        "exec /bin/bash -euo pipefail /workspace/scripts/clean.sh",
    )


def test_task_runtime_values_and_templates_are_resolved(tmp_path: Path):
    config = project(
        tmp_path,
        """diagnose:
  container: dev_${env:USER}
  script: /workspace/scripts/${date:%Y%m%d}/diagnose.sh
  environment:
    MODE: {default: quick, prompt: {mode: input, message: Mode}}
""",
    )

    plan = ExecuteTaskUseCase(RecordingBackend()).plan(
        "diagnose",
        ResolutionRequest(
            config,
            overrides={"tasks.diagnose.environment.MODE": "full"},
            interactive=False,
        ),
        environment={"USER": "root"},
    )

    assert plan.container == "dev_root"
    assert dict(plan.environment) == {"MODE": "full"}
    assert str(plan.script).startswith("/workspace/scripts/")
    assert str(plan.script).endswith("/diagnose.sh")


def test_menu_is_optional_and_label_must_not_be_blank(tmp_path: Path):
    config = project(
        tmp_path,
        "cli-only: {container: dev, script: /workspace/task.sh}\n",
    )
    assert load_config(config).tasks["cli-only"].menu is None

    invalid = project(
        tmp_path / "invalid",
        "bad: {container: dev, script: /workspace/task.sh, menu: {label: ' '}}\n",
    )
    with pytest.raises(SchemaValidationError, match="label"):
        load_config(invalid)


def test_task_can_disable_automatic_container_start(tmp_path: Path):
    config = project(
        tmp_path,
        "clean: {container: dev, start_container: false, script: /workspace/clean.sh}\n",
    )

    plan = ExecuteTaskUseCase(RecordingBackend()).plan(
        "clean", ResolutionRequest(config, interactive=False)
    )

    assert plan.start_container is False


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


def sample_plan() -> CommandPlan:
    return CommandPlan(
        task_name="clean",
        container="dev",
        script=Path("/workspace/clean.sh"),
        command=("docker", "exec", "dev", "/bin/sh", "-eu", "/workspace/clean.sh"),
        workdir=None,
        user=None,
        setup=(),
        environment=(),
        environment_overrides=(),
        timeout_seconds=30,
        tty="auto",
    )


def test_backend_streams_task_output_without_capture():
    runner = FakeRunner([ProcessResult(0, "true\n"), ProcessResult(0)])
    plan = sample_plan()

    result = DockerExecTaskBackend(runner).execute(plan)

    assert result.task_name == "clean"
    assert runner.calls[1] == (
        plan.command,
        {"capture": False, "timeout_seconds": 30},
    )


def test_backend_reports_process_and_infrastructure_errors():
    plan = sample_plan()
    with pytest.raises(CommandFailure, match="exit code 17"):
        DockerExecTaskBackend(FakeRunner([ProcessResult(0, "true\n"), ProcessResult(17)])).execute(
            plan
        )
    with pytest.raises(CommandFailure, match="timed out after 30 seconds"):
        DockerExecTaskBackend(
            FakeRunner([ProcessResult(0, "true\n"), subprocess.TimeoutExpired(plan.command, 30)])
        ).execute(plan)
    with pytest.raises(BackendUnavailableError, match="cannot execute Docker"):
        DockerExecTaskBackend(FakeRunner([FileNotFoundError("missing")])).execute(plan)


def test_backend_honours_disabled_container_start():
    plan = CommandPlan(**{**sample_plan().__dict__, "start_container": False})

    with pytest.raises(CommandFailure, match="is not running"):
        DockerExecTaskBackend(FakeRunner([ProcessResult(0, "false\n")])).execute(plan)


def test_cli_dry_run_does_not_execute(tmp_path: Path, monkeypatch, capsys):
    config = project(tmp_path, definition())

    class ForbiddenBackend:
        def execute(self, plan):
            raise AssertionError("dry-run must not execute")

    monkeypatch.setattr("rigyard.cli.commands.tasks.DockerExecTaskBackend", ForbiddenBackend)
    assert run(["--config", str(config), "task", "run", "clean", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Task: clean" in output
    assert "/workspace/scripts/clean.sh" in output
    assert "--env=CLEAN_INSTALL=REDACTED" in output
    assert "--env=CLEAN_INSTALL=false" not in output


def test_cli_runs_cli_only_task(tmp_path: Path, monkeypatch, capsys):
    config = project(
        tmp_path,
        "cli-only: {container: dev, script: /workspace/task.sh}\n",
    )
    backend = RecordingBackend()
    monkeypatch.setattr("rigyard.cli.commands.tasks.DockerExecTaskBackend", lambda: backend)

    assert run(["--config", str(config), "task", "run", "cli-only"]) == 0
    assert [plan.task_name for plan in backend.plans] == ["cli-only"]
    assert "completed" in capsys.readouterr().out


@pytest.mark.parametrize(("confirm", "answers"), [(True, "6\n1\ny\n"), (False, "6\n1\n")])
def test_menu_shows_only_enabled_tasks_and_honours_confirmation(
    tmp_path: Path, confirm: bool, answers: str
):
    config = project(
        tmp_path,
        definition(confirm=confirm) + "hidden:\n"
        "  container: dev\n"
        "  script: /workspace/hidden.sh\n"
        "  menu: {enabled: false, label: Hidden task}\n"
        "cli-only: {container: dev, script: /workspace/cli.sh}\n",
    )
    backend = RecordingBackend()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer(answers), output),
        task_backend_factory=lambda: backend,
    )

    assert app.run(config) == 0
    assert [plan.task_name for plan in backend.plans] == ["clean"]
    rendered = output.getvalue()
    assert "Clean workspace" in rendered
    assert "Hidden task" not in rendered
    assert "cli-only" not in rendered
    assert ("Run this task now?" in rendered) is confirm


def test_source_selected_prompt_accepts_explicit_override(tmp_path: Path):
    config = tmp_path / "rigyard.yaml"
    config.write_text("version: 3\nmetadata: {name: demo}\nsources: {tasks: [a.yaml, b.yaml]}\n")
    (tmp_path / "a.yaml").write_text("run: {container: a, script: /run.sh}\n")
    (tmp_path / "b.yaml").write_text(
        "run:\n  container: {prompt: {mode: input, message: Container}}\n  script: /run.sh\n"
    )
    from rigyard.application.requests import ResolutionRequest
    from rigyard.application.tasks import ExecuteTaskUseCase
    from rigyard.providers.docker import DockerExecTaskBackend

    plan = ExecuteTaskUseCase(DockerExecTaskBackend()).plan(
        "run",
        ResolutionRequest(
            config,
            interactive=False,
            source_path=Path("b.yaml"),
            overrides={"tasks.run.container": "b"},
        ),
    )
    assert plan.container == "b"
