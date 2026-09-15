import io
from pathlib import Path

import pytest

from toolchain.application.requests import ResolutionRequest
from toolchain.application.scenarios import PlanScenarioUseCase
from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.config.loader import load_config
from toolchain.errors import ScenarioExecutionError, ScenarioPlanError
from toolchain.execution import CommandResult
from toolchain.providers.supervisor import ComposeSupervisorBackend, render_supervisor_config
from toolchain.providers.tmux import TmuxScenarioBackend
from toolchain.scenarios.models import (
    ComposeSupervisorPlan,
    ScenarioGroupPlan,
    ScenarioResult,
    SupervisorOptionsSpec,
    TmuxScenarioPlan,
)


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(tmp_path: Path, scenarios: str) -> Path:
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 2
metadata: {name: scenario-test}
sources: {scenarios: config/scenarios.yaml}
""",
    )
    write(tmp_path / "config/scenarios.yaml", scenarios)
    return config


def scenario_yaml(compose_file: str = "deploy/compose.yaml") -> str:
    return f"""robot:
  description: Robot system
  groups:
    drivers:
      container: robot-dev
      service: robot
      script: /workspace/scenes/drivers.sh
      environment:
        ROS_DOMAIN_ID:
          default: "7"
          prompt: {{mode: input, message: ROS domain}}
    navigation:
      enabled: false
      container: robot-dev
      service: robot
      script:
        prompt: {{mode: input, message: Navigation script}}
  profiles:
    development:
      backend: tmux
      attach: false
    deployment:
      backend: compose-supervisor
      compose_file: {compose_file}
      supervisor_config_dir: deploy/generated
      project_name:
        prompt: {{mode: input, message: Compose project}}
"""


def test_load_scenario_only_project(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    loaded = load_config(config)
    assert loaded.sources.scenarios == Path("config/scenarios.yaml")
    assert list(loaded.scenarios["robot"].groups) == ["drivers", "navigation"]
    assert set(loaded.scenarios["robot"].profiles) == {"development", "deployment"}


def test_tmux_plan_is_lazy_across_profiles_and_disabled_groups(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())

    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
    )

    assert isinstance(plan, TmuxScenarioPlan)
    assert [group.name for group in plan.groups] == ["drivers"]
    assert dict(plan.groups[0].environment) == {"ROS_DOMAIN_ID": "7"}
    assert plan.session.startswith("tc-scenario-test-robot-")


def test_compose_plan_resolves_only_deployment_profile(tmp_path: Path):
    compose = write(tmp_path / "deploy/compose.yaml", "services: {}\n")
    config = project(tmp_path, scenario_yaml())

    plan = PlanScenarioUseCase().plan(
        "robot",
        "deployment",
        ResolutionRequest(
            config,
            overrides={"scenarios.robot.profiles.deployment.project_name": "robot-prod"},
            interactive=False,
        ),
    )

    assert isinstance(plan, ComposeSupervisorPlan)
    assert plan.compose_file == compose.resolve()
    assert plan.project_name == "robot-prod"
    assert plan.supervisor_config_dir == (tmp_path / "deploy/generated").resolve()


def test_profile_requires_backend_specific_group_target(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  groups:
    drivers: {script: /run.sh}
  profiles:
    development: {backend: tmux, attach: false}
""",
    )
    with pytest.raises(ScenarioPlanError, match="requires container"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_management_plan_does_not_resolve_group_runtime_fields(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  groups:
    drivers:
      container: robot-dev
      script: {prompt: {mode: input, message: Driver script}}
      environment:
        REQUIRED: {prompt: {mode: input, message: Required value}}
  profiles:
    development: {backend: tmux, attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        resolve_group_runtime=False,
    )
    assert isinstance(plan, TmuxScenarioPlan)
    assert [item.name for item in plan.groups] == ["drivers"]


class DispatchRunner:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        outcome = self.handler(command, kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def group(name: str, *, container: str = "robot-dev", service: str = "robot"):
    return ScenarioGroupPlan(
        name=name,
        container=container,
        service=service,
        script=f"/workspace/{name}.sh",
        interpreter=("/bin/bash", "-euo", "pipefail"),
        user=None,
        workdir="/workspace",
        environment=(("ROS_DOMAIN_ID", "7"),),
        supervisor=SupervisorOptionsSpec(),
    )


def tmux_plan(*groups: ScenarioGroupPlan, attach: bool = False, replace: bool = False):
    return TmuxScenarioPlan("robot", "development", "robot-session", attach, replace, 0, groups)


def test_tmux_start_preflights_container_and_creates_windows():
    def handler(command, _):
        if command[:2] == ("tmux", "has-session"):
            return CommandResult(1)
        if command[:3] == ("docker", "inspect", "--format={{.State.Running}}"):
            return CommandResult(0, "true\n")
        return CommandResult(0)

    runner = DispatchRunner(handler)
    plan = tmux_plan(group("drivers"), group("navigation"))
    result = TmuxScenarioBackend(runner).start(plan)

    assert result.detail == "tmux:robot-session"
    commands = [call[0] for call in runner.calls]
    assert (
        "tmux",
        "new-session",
        "-d",
        "-s",
        "robot-session",
        "-n",
        "drivers",
    ) in commands
    remain_commands = [command for command in commands if command[1] == "set-option"]
    assert len(remain_commands) == 2
    assert all(command[-2:] == ("remain-on-exit", "on") for command in remain_commands)
    process_commands = [command for command in commands if command[1] == "respawn-pane"]
    assert len(process_commands) == 2
    assert "docker exec -it" in process_commands[0][-1]
    assert "--env=ROS_DOMAIN_ID=7" in process_commands[0][-1]
    inspect_calls = [call for call in runner.calls if call[0][:2] == ("docker", "inspect")]
    assert len(inspect_calls) == 1


def test_tmux_existing_session_fails_without_replace():
    runner = DispatchRunner(
        lambda command, _: (
            CommandResult(0) if command[:2] == ("tmux", "has-session") else CommandResult(0)
        )
    )
    with pytest.raises(ScenarioExecutionError, match="already exists"):
        TmuxScenarioBackend(runner).start(tmux_plan(group("drivers")))


def test_tmux_partial_start_failure_cleans_new_session():
    def handler(command, _):
        if command[:2] == ("tmux", "has-session"):
            return CommandResult(1)
        if command[:2] == ("docker", "inspect"):
            return CommandResult(0, "true\n")
        if command[:2] == ("tmux", "new-window"):
            return CommandResult(9, stderr="failed")
        return CommandResult(0)

    runner = DispatchRunner(handler)
    with pytest.raises(ScenarioExecutionError, match="cannot create tmux window"):
        TmuxScenarioBackend(runner).start(tmux_plan(group("drivers"), group("navigation")))
    assert ("tmux", "kill-session", "-t", "robot-session") in [c[0] for c in runner.calls]


def test_tmux_stop_sends_interrupt_before_kill():
    runner = DispatchRunner(lambda *_: CommandResult(0))
    plan = tmux_plan(group("drivers"), group("navigation"))
    backend = TmuxScenarioBackend(runner, sleep_fn=lambda _: None)

    assert backend.stop(plan).detail == "stopped"
    commands = [call[0] for call in runner.calls]
    interrupts = [command for command in commands if command[:2] == ("tmux", "send-keys")]
    assert len(interrupts) == 2
    assert commands[-1] == ("tmux", "kill-session", "-t", "robot-session")


def compose_plan(tmp_path: Path, *groups: ScenarioGroupPlan) -> ComposeSupervisorPlan:
    compose = write(tmp_path / "compose.yaml", "services: {}\n")
    return ComposeSupervisorPlan(
        "robot",
        "deployment",
        compose,
        "robot-prod",
        tmp_path / "generated",
        groups,
    )


def test_supervisor_renderer_has_ros_friendly_shutdown_and_escaped_environment():
    options = SupervisorOptionsSpec(priority=20, stopwaitsecs=30)
    item = ScenarioGroupPlan(
        "navigation",
        "robot-dev",
        "robot",
        "/workspace/nav%2.sh",
        ("/bin/bash", "-eu"),
        "robot",
        "/workspace",
        (("VALUE", 'a%b"c'),),
        options,
    )
    rendered = render_supervisor_config((item,))
    assert "[program:navigation]" in rendered
    assert "nav%%2.sh" in rendered
    assert "stopsignal=INT" in rendered
    assert "stopasgroup=true" in rendered
    assert "killasgroup=true" in rendered
    assert 'environment=VALUE="a%%b\\"c"' in rendered
    assert "stdout_logfile=/dev/fd/1" in rendered


def test_compose_start_writes_service_configs_and_runs_up(tmp_path: Path):
    runner = DispatchRunner(lambda *_: CommandResult(0))
    plan = compose_plan(tmp_path, group("drivers"), group("navigation"))

    result = ComposeSupervisorBackend(runner).start(plan)

    assert result.detail == "compose:robot-prod"
    generated = (tmp_path / "generated/robot.conf").read_text()
    assert "[program:drivers]" in generated
    assert "[program:navigation]" in generated
    assert runner.calls[-1][0] == (
        "docker",
        "compose",
        "-f",
        str(plan.compose_file),
        "--project-name",
        "robot-prod",
        "up",
        "-d",
    )


def test_compose_start_removes_only_stale_generated_configs(tmp_path: Path):
    runner = DispatchRunner(lambda *_: CommandResult(0))
    generated = tmp_path / "generated"
    write(generated / "stale.conf", "; Generated by toolchain. Do not edit.\nold\n")
    manual = write(generated / "manual.conf", "[program:manual]\n")

    ComposeSupervisorBackend(runner).start(compose_plan(tmp_path, group("drivers")))

    assert not (generated / "stale.conf").exists()
    assert manual.read_text() == "[program:manual]\n"


def test_compose_status_and_group_logs(tmp_path: Path):
    def handler(command, _):
        if command[-1] == "ps":
            return CommandResult(0, "running\n")
        if "logs" in command:
            return CommandResult(0, "navigation log\n")
        return CommandResult(0)

    runner = DispatchRunner(handler)
    plan = compose_plan(tmp_path, group("navigation"))
    backend = ComposeSupervisorBackend(runner)
    assert backend.status(plan).detail == "running"
    assert backend.logs(plan, "navigation").detail == "navigation log"
    assert runner.calls[-1][0][-2:] == ("logs", "robot")
    with pytest.raises(ScenarioPlanError, match="only available for tmux"):
        backend.attach(plan)


def test_cli_dry_run_does_not_construct_backend(tmp_path: Path, monkeypatch, capsys):
    config = project(tmp_path, scenario_yaml())
    monkeypatch.setattr(
        "toolchain.cli.commands.scenarios.scenario_backend",
        lambda _: (_ for _ in ()).throw(AssertionError("must not construct backend")),
    )
    assert (
        run(
            [
                "--config",
                str(config),
                "scene",
                "start",
                "robot",
                "development",
                "--dry-run",
                "--replace",
                "--no-attach",
                "--non-interactive",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Backend: tmux" in output
    assert "Groups: drivers" in output
    assert "Attach after start: False" in output
    assert "Replace existing: True" in output


class FakeScenarioBackend:
    def __init__(self) -> None:
        self.started = []

    def start(self, plan):
        self.started.append(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name)


def test_menu_starts_scene_once_and_exits(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    backend = FakeScenarioBackend()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n1\n1\n\ny\n"), output),
        scenario_backend_factory=lambda _: backend,
    )
    assert app.run(config) == 0
    assert len(backend.started) == 1
    rendered = output.getvalue()
    assert rendered.count("Configuration:") == 1
    assert "Started scenario 'robot' profile 'development'" in rendered


def test_tmux_runner_os_error_is_actionable():
    runner = DispatchRunner(lambda *_: FileNotFoundError("missing"))
    with pytest.raises(Exception, match="cannot execute tmux"):
        TmuxScenarioBackend(runner).start(tmux_plan(group("drivers")))


def test_compose_runner_failure_is_actionable(tmp_path: Path):
    runner = DispatchRunner(
        lambda command, _: (
            CommandResult(8, stderr="compose failed")
            if command[-2:] == ("up", "-d")
            else CommandResult(0)
        )
    )
    with pytest.raises(ScenarioExecutionError, match="compose failed"):
        ComposeSupervisorBackend(runner).start(compose_plan(tmp_path, group("drivers")))


def test_following_compose_logs_does_not_capture(tmp_path: Path):
    runner = DispatchRunner(lambda *_: CommandResult(0))
    plan = compose_plan(tmp_path, group("drivers"))
    ComposeSupervisorBackend(runner).logs(plan, follow=True)
    assert runner.calls[-1][1]["capture"] is False
    assert "--follow" in runner.calls[-1][0]
