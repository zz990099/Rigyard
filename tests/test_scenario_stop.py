"""Complete scene shutdown across runtime records, Docker, tmux and frontends."""

import io
from dataclasses import replace

import pytest
from test_scenario_records import plan_at
from test_scenarios import (
    FakeTmux,
    executor,
    instance,
    project,
    scenario_plan,
    scenario_yaml,
    write,
)

from rigyard.application.requests import ResolutionRequest
from rigyard.application.scenarios import PlanScenarioUseCase
from rigyard.cli.commands import scenarios as scenario_commands
from rigyard.cli.main import build_parser, run
from rigyard.errors import MissingValueError, ScenarioExecutionError, ScenarioPlanError
from rigyard.execution import CommandResult
from rigyard.scenarios.executor import ScenarioExecutor
from rigyard.scenarios.models import ScenarioComposePlan, ScenarioControlPlan, ScenarioResult
from rigyard.scenarios.records import FileRunStore, ScenarioRunRecord
from rigyard.scenarios.service import ScenarioService


@pytest.mark.parametrize("compose", [False, True])
def test_stop_interrupts_waits_cleans_environment_then_closes_tmux(tmp_path, compose):
    fake = FakeTmux(session=True, windows=("robot1",))
    plan = replace(
        scenario_plan(
            instance(service="robot") if compose else instance(),
            compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-project", 60)
            if compose
            else None,
        ),
        stop_grace_seconds=5,
    )

    def wait(seconds):
        assert seconds == 5
        assert fake.commands[-1][-1] == "C-c"
        assert not any(command[:2] == ("docker", "stop") for command in fake.commands)
        assert not any("down" in command for command in fake.commands)
        fake.calls.append((("wait", str(seconds)), {}))

    ScenarioExecutor(fake, sleep_fn=wait).stop(plan)
    cleanup_index = next(
        index
        for index, command in enumerate(fake.commands)
        if command[:2] == ("docker", "stop") or "down" in command
    )
    kill = ("tmux", "kill-session", "-t", plan.session)
    assert fake.commands.index(("wait", "5")) < cleanup_index < fake.commands.index(kill)
    assert not any("--volumes" in command or "--rmi" in command for command in fake.commands)


@pytest.mark.parametrize("compose", [False, True])
def test_stop_cleans_environment_without_tmux_and_can_be_repeated(tmp_path, compose):
    fake = FakeTmux()
    plan = scenario_plan(
        instance(service="robot") if compose else instance(),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-project", 60)
        if compose
        else None,
    )
    backend = executor(fake)
    assert backend.stop(plan).detail == "stopped"
    assert backend.stop(plan).detail == "stopped"
    cleanup = [
        command
        for command in fake.commands
        if command[:2] == ("docker", "stop") or "down" in command
    ]
    assert len(cleanup) == 2
    assert not any(command[:2] == ("tmux", "kill-session") for command in fake.commands)


def test_stop_deduplicates_containers_and_includes_instances_without_windows():
    fake = FakeTmux(session=True, windows=("one",))
    executor(fake).stop(
        scenario_plan(
            instance("one", container="shared"),
            instance("two", container="shared"),
            instance("three", container="other"),
        )
    )
    assert [command for command in fake.commands if command[:2] == ("docker", "stop")] == [
        ("docker", "stop", "shared"),
        ("docker", "stop", "other"),
    ]


def test_stop_attempts_remaining_containers_after_one_fails():
    fake = FakeTmux(session=True, windows=("one", "two"))

    def fail_first(command, _kwargs):
        if command == ("docker", "stop", "first"):
            return CommandResult(1, stderr="first is busy")
        return None

    fake.override = fail_first
    plan = scenario_plan(instance("one", container="first"), instance("two", container="second"))
    with pytest.raises(ScenarioExecutionError, match="first is busy"):
        executor(fake).stop(plan)
    assert ("docker", "stop", "second") in fake.commands
    assert not fake.session


@pytest.mark.parametrize("compose", [False, True])
def test_failed_cleanup_closes_tmux_keeps_record_and_can_be_retried(tmp_path, compose):
    fake = FakeTmux(session=True, windows=("robot1",))
    plan = plan_at(
        tmp_path,
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-project", 60)
        if compose
        else None,
    )
    store = FileRunStore(plan.identity.config_path)
    target = ScenarioControlPlan.from_start(plan)
    store.write(ScenarioRunRecord(state="failed", target=target))

    def fail_cleanup(command, _kwargs):
        if command[:2] == ("docker", "stop") or "down" in command:
            return CommandResult(1, stderr="resource busy")
        return None

    fake.override = fail_cleanup
    service = ScenarioService(executor(fake))
    with pytest.raises(ScenarioExecutionError, match="resource busy"):
        service.stop(target)
    assert not fake.session
    assert store.records()[0].target == target
    fake.override = None
    service.stop(target)
    assert store.records() == ()


def test_tmux_cleanup_failure_keeps_record_after_container_stop(tmp_path):
    fake = FakeTmux(session=True, windows=("robot1",))
    plan = plan_at(tmp_path)
    store = FileRunStore(plan.identity.config_path)
    target = ScenarioControlPlan.from_start(plan)
    store.write(ScenarioRunRecord(state="running", target=target))

    def fail_kill(command, _kwargs):
        if command[:2] == ("tmux", "kill-session"):
            return CommandResult(1, stderr="cannot kill session")
        return None

    fake.override = fail_kill
    service = ScenarioService(executor(fake))
    with pytest.raises(ScenarioExecutionError, match="cannot kill session"):
        service.stop(target)
    assert ("docker", "stop", "robot-dev") in fake.commands
    assert len(store.records()) == 1
    fake.override = None
    service.stop(target)
    assert not fake.session
    assert store.records() == ()


def test_stop_uses_recorded_container_instead_of_changed_configuration(tmp_path):
    config = project(tmp_path, scenario_yaml())
    request = ResolutionRequest(config, interactive=False)
    plan = PlanScenarioUseCase().plan("robot", "development", request)
    fake = FakeTmux()
    service = ScenarioService(executor(fake))
    service.start(plan)
    write(tmp_path / "config/scenarios.yaml", scenario_yaml().replace("robot-dev", "replacement"))
    target = PlanScenarioUseCase().plan("robot", None, request, operation="stop")
    assert target.instances[0].container == "robot-dev"
    service.stop(target)
    assert ("docker", "stop", "robot-dev") in fake.commands
    assert ("docker", "stop", "replacement") not in fake.commands


def test_stop_without_record_resolves_only_enabled_container_targets(tmp_path):
    config = project(
        tmp_path,
        """robot:
  instances:
    one:
      container: {default: '${env:SCENE_CONTAINER}', prompt: {mode: input, message: Container}}
      groups: {driver: {script: {prompt: {mode: input, message: Script}}}}
    disabled:
      enabled: false
      container: {prompt: {mode: input, message: Disabled container}}
      groups: {driver: {command: [echo, unused]}}
  profiles:
    development:
      attach: {prompt: {mode: confirm, message: Attach}}
      restart_container: never
""",
    )
    target = PlanScenarioUseCase().plan(
        "robot",
        None,
        ResolutionRequest(config, interactive=False),
        operation="stop",
        environment={"SCENE_CONTAINER": "original-container"},
    )
    assert [(item.name, item.container) for item in target.instances] == [
        ("one", "original-container")
    ]
    assert target.stop_grace_seconds == 5


def test_stop_requires_container_values_when_no_record_exists(tmp_path):
    config = project(
        tmp_path,
        scenario_yaml().replace(
            "container: robot-dev", "container: {prompt: {mode: input, message: Container}}"
        ),
    )
    with pytest.raises(MissingValueError, match="robot1.container"):
        PlanScenarioUseCase().plan(
            "robot", None, ResolutionRequest(config, interactive=False), operation="stop"
        )


def test_compose_stop_does_not_resolve_startup_wait_timeout(tmp_path):
    config = project(
        tmp_path,
        scenario_yaml()
        .replace(
            "  description: Robot system",
            "  compose:\n    file: compose.yaml\n"
            "    wait_timeout_seconds: {prompt: {mode: input, message: Startup wait}}",
        )
        .replace("container: robot-dev", "service: robot"),
    )
    write(tmp_path / "compose.yaml", "services: {robot: {image: ubuntu}}\n")
    target = PlanScenarioUseCase().plan(
        "robot", None, ResolutionRequest(config, interactive=False), operation="stop"
    )
    assert target.compose is not None


@pytest.mark.parametrize(
    "args", [["scene", "down", "robot"], ["scene", "stop", "robot", "--instance", "one"]]
)
def test_cli_rejects_down_and_partial_stop(args):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(args)
    assert error.value.code == 2


def test_partial_stop_is_rejected_before_loading_configuration(tmp_path):
    with pytest.raises(ScenarioPlanError, match="does not support partial"):
        PlanScenarioUseCase().plan(
            "robot",
            None,
            ResolutionRequest(tmp_path / "missing.yaml"),
            operation="stop",
            instances=["one"],
        )


def test_cli_stop_dispatches_complete_resolved_target(tmp_path, monkeypatch):
    config = project(tmp_path, scenario_yaml())
    targets = []

    class Service:
        def stop(self, target):
            targets.append(target)
            return ScenarioResult(target.scene_name, target.profile_name, "stopped")

    monkeypatch.setattr(scenario_commands, "_service", Service)
    output = io.StringIO()
    assert (
        run(["--config", str(config), "scene", "stop", "robot", "--non-interactive"], stdout=output)
        == 0
    )
    assert not targets[0].partial
    assert targets[0].instances[0].container == "robot-dev"
    assert output.getvalue() == "stopped\n"


def test_partial_start_with_never_policy_does_not_stop_any_containers():
    fake = FakeTmux(session=True, windows=("robot1", "other"))
    plan = scenario_plan(instance(), partial=True, restart_container="never")
    executor(fake).start(plan)
    assert not any(command[:2] == ("docker", "stop") for command in fake.commands)
    assert fake.windows == ["other", "robot1"]
