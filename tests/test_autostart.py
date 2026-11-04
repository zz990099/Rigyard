import io
import json
import os
import shlex
from dataclasses import replace

import pytest
from test_scenario_records import plan_at
from test_scenarios import FakeTmux, TTYBuffer, executor, project, scenario_yaml

from rigyard.application.autostart import (
    PlanAutostartUseCase,
    autostart_status,
    selected_unit,
    unit_name,
)
from rigyard.application.project import ProjectContext
from rigyard.application.requests import ResolutionRequest
from rigyard.application.scenarios import PlanScenarioUseCase
from rigyard.autostart.systemd import MARKER, SystemdManager, quote, validate_unit
from rigyard.cli.commands import autostart as cli
from rigyard.cli.main import run
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.cli.menu.session import MenuSession
from rigyard.errors import ScenarioExecutionError, ScenarioPlanError
from rigyard.execution import CommandResult
from rigyard.scenarios.models import ScenarioControlPlan
from rigyard.scenarios.records import FileRunStore, ScenarioRunRecord
from rigyard.scenarios.runtime import ScenarioCommandGateway
from rigyard.scenarios.service import ScenarioService
from rigyard.scenarios.tmux import TmuxSessionBackend


class SocketFake(FakeTmux):
    def run(self, command, **kwargs):
        if command[:2] == ("tmux", "-L"):
            command = ("tmux", *command[3:])
        return super().run(command, **kwargs)


UNIT = "rigyard-autostart-" + "a" * 64 + ".service"


@pytest.fixture(autouse=True)
def fake_install_privileges(monkeypatch):
    # Unit tests inspect argv without invoking sudo; integration tests use real privileges.
    monkeypatch.setattr(os, "geteuid", lambda: 0)


def boot_plan(tmp_path, yaml=None, **kwargs):
    config = project(tmp_path, yaml or scenario_yaml())
    return PlanAutostartUseCase().plan(
        "robot",
        None,
        ResolutionRequest(config, interactive=False, workspace_root=tmp_path, **kwargs),
    )


def test_plan_reuses_definition_and_embeds_typed_answers(tmp_path):
    planned = boot_plan(tmp_path)
    assert planned.unit == unit_name(planned.scenario.identity)
    assert "Type=oneshot" in planned.content
    assert "RemainAfterExit=yes" in planned.content
    assert "ExecStopPost=" in planned.content
    assert "WantedBy=multi-user.target" in planned.content
    assert '"-m" "rigyard"' in planned.content
    assert "--workspace-root" in planned.content
    assert not (tmp_path / ".rigyard").exists()
    # JSON quoting protects strings such as "7" from YAML scalar coercion.
    line = next(line for line in planned.content.splitlines() if line.startswith("ExecStart="))
    argv = shlex.split(line.split("=", 1)[1])
    path, value = argv[argv.index("--set") + 1].split("=", 1)
    assert path.endswith(".ROS_DOMAIN_ID")
    assert json.loads(value) == "7"
    assert "--non-interactive" in argv
    assert '"User=' not in planned.content


def test_raw_replay_does_not_apply_append_or_input_template_twice(tmp_path):
    yaml = """robot:
  instances:
    robot1:
      container:
        prompt: {mode: select, message: Container, source: {provider: docker-containers}}
      groups:
        run:
          command: [echo, hello]
          setup:
            base: [/base.sh]
            prompt: {mode: input, message: Setup, repeat: true, merge: append,
                     input_template: "/opt/${INPUT}.sh"}
  profiles: {custom: {attach: false}}
"""
    config = project(tmp_path, yaml)
    request = ResolutionRequest(
        config,
        interactive=False,
        overrides={
            "scenarios.robot.instances.robot1.container": "dev",
            "scenarios.robot.instances.robot1.groups.run.setup": ["one", "two"],
        },
        workspace_root=tmp_path,
    )
    answers = {}
    first = PlanScenarioUseCase().plan("robot", None, request, answers=answers)
    second = PlanScenarioUseCase().plan("robot", None, replace(request, overrides=answers))
    assert first == second
    assert first.instances[0].groups[0].setup == ("/base.sh", "/opt/one.sh", "/opt/two.sh")
    assert answers["scenarios.robot.instances.robot1.groups.run.setup"] == ["one", "two"]
    assert PlanAutostartUseCase().plan("robot", None, request).scenario == first


def test_dynamic_container_only_prompts_during_enable(tmp_path):
    yaml = scenario_yaml().replace(
        "container: robot-dev",
        """container:
        prompt: {mode: select, source: {provider: docker-containers}, message: Container}""",
    )
    config = project(tmp_path, yaml)
    from rigyard.parameters.sources import DynamicOption

    calls = []
    answers = iter(["1", ""])
    planned = PlanAutostartUseCase(
        sources={
            "docker-containers": lambda source: (
                calls.append(source) or [DynamicOption("dev", "dev")]
            ),
        }
    ).plan(
        "robot",
        None,
        ResolutionRequest(config, input_fn=lambda _: next(answers), workspace_root=tmp_path),
    )
    assert len(calls) == 1
    assert planned.scenario.instances[0].container == "dev"


def test_environment_and_workspace_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOT_TEST", "value with % and $")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-copy")
    planned = boot_plan(
        tmp_path,
        scenario_yaml().replace(
            "/ros2_ws/drivers.sh", "${WORKSPACE_ROOT}/${env:ROBOT_TEST}/drivers.sh"
        ),
    )
    assert "ROBOT_TEST=value with %% and $" in planned.content
    assert "UNRELATED_SECRET" not in planned.content
    assert f'WorkingDirectory="{tmp_path}"' in planned.content


def test_date_template_remains_in_yaml_not_frozen_in_unit(tmp_path):
    planned = boot_plan(
        tmp_path, scenario_yaml().replace("/ros2_ws/drivers.sh", "/logs/${date:%Y%m%d}/run.sh")
    )
    assert "/logs/" not in planned.content


@pytest.mark.parametrize("value", ["hello world", "中文", '"quotes"', r"c:\path", "$HOME", "%i"])
def test_systemd_quoting(value):
    escaped = quote(value, command=True)
    decoded = shlex.split(escaped)[0].replace("%%", "%").replace("$$", "$")
    assert decoded == value


@pytest.mark.parametrize("value", ["bad\nExecStart=x", "bad\r", "\0", "\t"])
def test_reject_unit_directive_injection(value):
    with pytest.raises(ScenarioPlanError, match="control characters"):
        quote(value)


@pytest.mark.parametrize("value", ["docker.service", "../bad", UNIT + "\n", ""])
def test_reject_foreign_unit_names(value):
    with pytest.raises(ScenarioPlanError):
        validate_unit(value)


class Runner:
    def __init__(
        self, state="LoadState=loaded\nUnitFileState=disabled\nActiveState=inactive", fail=None
    ):
        self.calls = []
        self.state = state
        self.fail = fail

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.fail and self.fail in command:
            self.fail = None
            return CommandResult(1, stderr="injected failure")
        if command[:2] == ("systemctl", "show"):
            return CommandResult(0, stdout=self.state)
        return CommandResult(0, stdout="ok")


def registered(tmp_path, unit=UNIT, **metadata):
    path = tmp_path / unit
    path.write_text(MARKER + json.dumps({"unit": unit, **metadata}) + "\n[Service]\n")
    return path


def test_manager_enable_and_disable_do_not_start_or_stop_by_default(tmp_path):
    runner = Runner()
    manager = SystemdManager(runner, tmp_path)
    manager.install(UNIT, "[Service]\n")
    commands = [c for c, _ in runner.calls]
    assert ("systemctl", "enable", UNIT) in commands
    assert ("systemctl", "start", UNIT) not in commands
    registered(tmp_path)
    manager.disable(UNIT)
    assert runner.calls[-1][0] == ("systemctl", "disable", UNIT)
    manager.disable(UNIT, now=True)
    assert runner.calls[-1][0] == ("systemctl", "disable", "--now", UNIT)
    manager.stop(UNIT)
    assert runner.calls[-1][0] == ("systemctl", "stop", UNIT)


def test_manager_now_and_sudo_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    runner = Runner()
    manager = SystemdManager(runner, tmp_path)
    manager.install(UNIT, "[Service]\n", now=True)
    assert runner.calls[-1][0] == ("sudo", "--", "systemctl", "start", UNIT)


def test_manager_rejects_active_update_and_unmanaged_file(tmp_path):
    path = registered(tmp_path)
    manager = SystemdManager(Runner(state="ActiveState=active"), tmp_path)
    with pytest.raises(ScenarioPlanError, match="stop the running"):
        manager.install(UNIT, "new")
    path.write_text("[Service]\n")
    with pytest.raises(ScenarioPlanError, match="cannot read Rigyard unit"):
        manager.install(UNIT, "new")


@pytest.mark.parametrize("old", [False, True])
def test_manager_rolls_back_failed_registration(tmp_path, old):
    if old:
        registered(tmp_path)
    runner = Runner(fail="enable")
    manager = SystemdManager(runner, tmp_path)
    with pytest.raises(ScenarioExecutionError, match="injected failure"):
        manager.install(UNIT, "new")
    commands = [c for c, _ in runner.calls]
    assert commands.count(("systemctl", "daemon-reload")) == 2
    if not old:
        assert ("rm", "-f", "--", str(tmp_path / UNIT)) in commands


def test_socket_covers_control_and_cleanup_and_cross_server_attach():
    runner = Runner()
    backend = TmuxSessionBackend(
        ScenarioCommandGateway(runner), runner, {"TMUX": "another"}, "boot"
    )
    backend.require()
    backend.session_exists("robot")
    backend.interrupt("robot:0.0")
    backend.kill_session("robot", checked=False)
    backend.attach("robot")
    assert all(c[:3] == ("tmux", "-L", "boot") for c, _ in runner.calls)
    assert runner.calls[-1][0][3] == "attach-session"


def test_manual_and_boot_runs_cannot_replace_each_other(tmp_path):
    plan = plan_at(tmp_path)
    fake = SocketFake()
    manual = ScenarioService(executor(fake))
    manual.start(plan)
    boot = replace(plan, owner_unit=UNIT, tmux_socket="boot")
    with pytest.raises(ScenarioPlanError, match="another owner"):
        ScenarioService(executor(fake), owner_unit=UNIT).start(boot)
    manual.stop(plan)
    ScenarioService(executor(fake), owner_unit=UNIT).start(boot)
    with pytest.raises(ScenarioPlanError, match="another owner"):
        manual.start(plan)
    record = FileRunStore(plan.identity.config_path).records()[0]
    assert record.target.owner_unit == UNIT
    assert record.target.tmux_socket == "boot"


def test_previous_boot_record_does_not_prevent_autostart(tmp_path):
    plan = plan_at(tmp_path)
    store = FileRunStore(plan.identity.config_path)
    store.write(
        ScenarioRunRecord(
            state="running", boot_id="previous-boot", target=ScenarioControlPlan.from_start(plan)
        )
    )
    boot = replace(plan, owner_unit=UNIT, tmux_socket="boot")
    ScenarioService(executor(SocketFake()), owner_unit=UNIT).start(boot)
    assert store.records()[0].target.owner_unit == UNIT


def test_stop_scene_routes_to_systemd_without_holding_lifecycle_lock(tmp_path, monkeypatch):
    plan = replace(plan_at(tmp_path), owner_unit=UNIT, tmux_socket="boot")
    fake = SocketFake()
    managed = ScenarioService(executor(fake), owner_unit=UNIT)
    managed.start(plan)
    called = []

    def stop(manager, unit):
        called.append(unit)
        managed.stop(plan)

    monkeypatch.setattr(SystemdManager, "stop", stop)
    ScenarioService(executor(fake)).stop(plan)
    assert called == [UNIT]
    assert not FileRunStore(plan.identity.config_path).records()


def test_other_boot_scene_cannot_share_existing_container(tmp_path):
    plan = replace(plan_at(tmp_path), owner_unit=UNIT, tmux_socket="one")
    fake = SocketFake()
    service = ScenarioService(executor(fake), owner_unit=UNIT)
    service.start(plan)
    other = replace(
        plan,
        identity=replace(plan.identity, profile_name="other"),
        session="other",
        tmux_socket="two",
    )
    with pytest.raises(ScenarioPlanError, match="another recorded"):
        service.start(other)


def test_cli_dry_run_does_not_modify_system(tmp_path):
    config = project(tmp_path, scenario_yaml())
    output = io.StringIO()
    assert (
        run(
            [
                "--config",
                str(config),
                "scene",
                "autostart",
                "enable",
                "robot",
                "--non-interactive",
                "--dry-run",
            ],
            stdout=output,
        )
        == 0
    )
    assert MARKER in output.getvalue()
    assert not (tmp_path / ".rigyard").exists()


def test_cli_internal_start_and_stop_work_without_source_on_stop(tmp_path, monkeypatch):
    planned = boot_plan(tmp_path)
    fake = SocketFake()
    monkeypatch.setattr("rigyard.scenarios.executor.ScenarioExecutor", lambda: executor(fake))
    start = next(line for line in planned.content.splitlines() if line.startswith("ExecStart="))
    argv = shlex.split(start.split("=", 1)[1])[3:]
    assert run(argv, stdout=io.StringIO()) == 0
    (tmp_path / "config/scenarios.yaml").unlink()
    stop = [
        "--config",
        str(tmp_path / "rigyard.yaml"),
        "scene",
        "autostart",
        "_stop",
        "--unit",
        planned.unit,
    ]
    assert run(stop) == 0
    assert run(stop) == 0
    assert not fake.session


def test_cleanup_never_stops_manual_run(tmp_path, monkeypatch):
    plan = plan_at(tmp_path)
    fake = SocketFake()
    ScenarioService(executor(fake)).start(plan)
    before = len(fake.commands)
    assert (
        run(
            [
                "--config",
                str(plan.identity.config_path),
                "scene",
                "autostart",
                "_stop",
                "--unit",
                UNIT,
            ]
        )
        == 0
    )
    assert len(fake.commands) == before


def test_selected_unit_and_status_need_no_container_prompts(tmp_path):
    config = project(tmp_path, scenario_yaml())
    request = ResolutionRequest(config, interactive=False)
    unit = selected_unit("robot", None, request)
    assert unit.startswith("rigyard-autostart-")
    manager = SystemdManager(Runner(), tmp_path)
    registered(tmp_path, unit, config=str(config))
    assert "Scene: no recorded run" in autostart_status(unit, manager)


def test_menu_reuses_scenario_selection(tmp_path, monkeypatch):
    config = project(tmp_path, scenario_yaml())
    output = TTYBuffer()
    # Autostart Enable -> file -> scene -> accept default ROS domain -> confirm.
    app = MenuApp(MenuIO(TTYBuffer("1\n1\n1\n\ny\n"), output))
    calls = []
    monkeypatch.setattr("rigyard.application.autostart.preflight", lambda *args: None)
    monkeypatch.setattr(
        SystemdManager, "install", lambda self, unit, content: calls.append(content)
    )
    app._autostart_menu(MenuSession(ProjectContext.capture(config)))
    assert len(calls) == 1
    assert "ExecStart=" in calls[0]
    assert "current run unchanged" in output.getvalue()


@pytest.mark.parametrize("compose", [False, True])
def test_preflight_checks_without_starting_containers(tmp_path, monkeypatch, compose):
    from rigyard.application.autostart import preflight

    planned = boot_plan(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    runner = Runner()
    manager = SystemdManager(runner, tmp_path)
    if compose:
        from rigyard.scenarios.models import ScenarioComposePlan

        planned = replace(
            planned,
            scenario=replace(
                planned.scenario, compose=ScenarioComposePlan(tmp_path / "compose.yaml", "ci", 60)
            ),
        )
        checked = []
        monkeypatch.setattr(
            "rigyard.scenarios.lifecycle.ComposeLifecycleBackend.preflight",
            lambda self, plan: checked.append(plan),
        )
    preflight(planned, manager)
    commands = [cmd for cmd, _ in runner.calls]
    assert ("docker", "info") in commands
    assert not any("start" in cmd or "restart" in cmd or "up" in cmd for cmd in commands)
    if compose:
        assert checked == [planned.scenario]
    else:
        assert ("docker", "inspect", "robot-dev") in commands


def test_preflight_rejects_missing_tools_and_remote_docker(tmp_path, monkeypatch):
    from rigyard.application.autostart import preflight

    planned = boot_plan(tmp_path)
    manager = SystemdManager(Runner(), tmp_path)
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(ScenarioPlanError, match="requires systemctl"):
        preflight(planned, manager)
    monkeypatch.setattr("shutil.which", lambda name: name)
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote:2375")
    with pytest.raises(ScenarioPlanError, match="local system Docker"):
        preflight(planned, manager)


@pytest.mark.parametrize("action", ["enable", "disable", "status"])
def test_cli_registration_actions(tmp_path, monkeypatch, action):
    config = project(tmp_path, scenario_yaml())
    output = io.StringIO()
    calls = []
    monkeypatch.setattr(cli, "preflight", lambda *args: None)
    monkeypatch.setattr(
        SystemdManager, "install", lambda self, unit, content, now=False: calls.append((unit, now))
    )
    monkeypatch.setattr(
        SystemdManager, "disable", lambda self, unit, now=False: calls.append((unit, now))
    )
    monkeypatch.setattr(
        "rigyard.application.autostart.autostart_status", lambda unit, manager: f"Status: {unit}"
    )
    argv = ["--config", str(config), "scene", "autostart", action, "robot"]
    if action == "enable":
        argv += ["--non-interactive", "--now"]
    assert run(argv, stdout=output) == 0
    if action == "status":
        assert "Status: rigyard-autostart-" in output.getvalue()
    else:
        assert calls[0][1] == (action == "enable")


@pytest.mark.parametrize(
    "argv",
    [
        ["enable"],
        ["disable"],
        ["enable", "robot", "--unit", UNIT],
    ],
)
def test_cli_missing_or_inconsistent_selection_is_rejected(tmp_path, argv):
    config = project(tmp_path, scenario_yaml())
    with pytest.raises(SystemExit):
        run(["--config", str(config), "scene", "autostart", *argv], stdout=io.StringIO())


def test_internal_start_rejects_wrong_unit_before_execution(tmp_path):
    config = project(tmp_path, scenario_yaml())
    errors = io.StringIO()
    assert (
        run(
            ["--config", str(config), "scene", "autostart", "_start", "robot", "--unit", UNIT],
            stderr=errors,
        )
        == 3
    )
    assert "does not match" in errors.getvalue()
    assert not (tmp_path / ".rigyard").exists()


def test_status_includes_live_scene_and_container_state(tmp_path, monkeypatch):
    from rigyard.scenarios.models import ScenarioResult

    plan = replace(plan_at(tmp_path), owner_unit=UNIT, tmux_socket="boot")
    fake = SocketFake()
    ScenarioService(executor(fake), owner_unit=UNIT).start(plan)
    registered(tmp_path, config=str(plan.identity.config_path))
    monkeypatch.setattr(
        ScenarioService,
        "status",
        lambda self, target: ScenarioResult("robot", "development", "pane live"),
    )
    text = autostart_status(UNIT, SystemdManager(Runner(), tmp_path))
    assert "Recorded state: running" in text
    assert "pane live" in text
    assert "ActiveState=" in text
    # Record is sufficient for menu/CLI selection even after YAML has gone.
    assert selected_unit("robot", None, ResolutionRequest(plan.identity.config_path)) == UNIT


@pytest.mark.parametrize("selection", ["2", "3"])
def test_menu_disable_and_status_never_prompt_for_values(tmp_path, monkeypatch, selection):
    config = project(tmp_path, scenario_yaml())
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer(selection + "\n1\n1\ny\n"), output))
    calls = []
    monkeypatch.setattr(SystemdManager, "disable", lambda self, unit: calls.append(unit))
    monkeypatch.setattr(
        "rigyard.application.autostart.autostart_status", lambda unit, manager: f"Status: {unit}"
    )
    app._autostart_menu(MenuSession(ProjectContext.capture(config)))
    assert "ROS domain" not in output.getvalue()
    assert calls or "Status: rigyard-autostart-" in output.getvalue()


def test_socket_does_not_follow_shell_tmux_tmpdir(monkeypatch):
    monkeypatch.setenv("TMUX_TMPDIR", "/different/server")
    runner = Runner()
    backend = TmuxSessionBackend(ScenarioCommandGateway(runner), runner, {}, "boot")
    backend.require()
    assert "TMUX_TMPDIR" not in runner.calls[-1][1]["environment"]
