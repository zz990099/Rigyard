from dataclasses import replace
from pathlib import Path

import pytest
from test_scenarios import FakeTmux, executor, group, instance, scenario_plan

from rigyard.application.requests import ResolutionRequest
from rigyard.application.scenarios import PlanScenarioUseCase
from rigyard.errors import ScenarioExecutionError, ScenarioPlanError
from rigyard.scenarios.identity import ScenarioIdentity
from rigyard.scenarios.models import ScenarioComposePlan, ScenarioControlPlan
from rigyard.scenarios.records import FileRunStore, ScenarioRunRecord, select_recorded_target
from rigyard.scenarios.service import ScenarioService


def plan_at(tmp_path: Path, **kwargs):
    return replace(
        scenario_plan(
            instance(groups=(group("run", environment=(("SECRET", "hidden"),)),)), **kwargs
        ),
        identity=ScenarioIdentity(
            tmp_path / "rigyard.yaml", tmp_path / "scene.yaml", "robot", "development"
        ),
    )


def test_recorded_control_survives_missing_configuration_and_has_no_scripts(tmp_path: Path):
    plan = plan_at(tmp_path)
    fake = FakeTmux()
    service = ScenarioService(executor(fake))
    service.start(plan)
    path = tmp_path / ".rigyard/runs" / f"{plan.identity.key}.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert "hidden" not in path.read_text()
    assert "/workspace/" not in path.read_text()
    request = ResolutionRequest(tmp_path / "rigyard.yaml", interactive=False)
    target = PlanScenarioUseCase().plan("robot", None, request, operation="logs")
    assert isinstance(target, ScenarioControlPlan)
    assert [item.name for item in target.instances[0].groups] == ["run"]
    assert service.logs(target).detail == "pane output"
    service.stop(target)
    assert not fake.session
    assert FileRunStore(request.config_path).records()[0].state == "stopped"


def test_partial_start_merges_recorded_instances(tmp_path: Path):
    fake = FakeTmux()
    service = ScenarioService(executor(fake))
    plan = plan_at(tmp_path)
    service.start(plan)
    second = replace(plan, instances=(instance("second"),), partial=True)
    service.start(second)
    record = FileRunStore(plan.identity.config_path).records()[0]
    assert [i.name for i in record.target.instances] == ["robot1", "second"]
    selected = select_recorded_target(record, ["second"])
    service.stop(selected)
    assert fake.windows == ["robot1"]
    with pytest.raises(ScenarioPlanError, match="unknown recorded"):
        select_recorded_target(record, ["missing"])


def test_failed_start_keeps_record_for_control_and_compose_down(tmp_path: Path):
    fake = FakeTmux()
    fake.dead["robot-session:robot1.0"] = 127
    service = ScenarioService(executor(fake))
    plan = plan_at(tmp_path)
    with pytest.raises(ScenarioExecutionError, match="exit 127"):
        service.start(plan)
    store = FileRunStore(plan.identity.config_path)
    record = store.records()[0]
    assert record.state == "failed"
    service.stop(record.target)
    assert not fake.session
    compose = ScenarioComposePlan(tmp_path / "compose.yaml", "robot-project", 30)
    target = replace(record.target, compose=compose)
    store.write(ScenarioRunRecord(state="stopped", target=target))
    service.down(target)
    assert not store.records()
    assert any("down" in command for command in fake.commands)


def test_record_conflicts_are_rejected_before_runtime_mutation(tmp_path: Path):
    fake = FakeTmux()
    service = ScenarioService(executor(fake))
    plan = plan_at(tmp_path)
    service.start(plan)
    before = len(fake.commands)
    other = replace(plan, identity=replace(plan.identity, profile_name="other"))
    with pytest.raises(ScenarioPlanError, match="another recorded"):
        service.start(other)
    assert len(fake.commands) == before
    with pytest.raises(ScenarioPlanError, match="runtime identity changed"):
        service.start(replace(plan, session="different"))
    with pytest.raises(ScenarioPlanError, match="partial start"):
        service.start(
            replace(plan, partial=True, compose=ScenarioComposePlan(tmp_path / "c.yaml", "c", 10))
        )


def test_corrupt_and_ambiguous_records_are_not_silently_ignored(tmp_path: Path):
    plan = plan_at(tmp_path)
    store = FileRunStore(plan.identity.config_path)
    target = ScenarioControlPlan.from_start(plan)
    store.write(ScenarioRunRecord(state="running", target=target))
    second = replace(
        target, profile_name="other", identity=replace(plan.identity, profile_name="other")
    )
    store.write(ScenarioRunRecord(state="running", target=second))
    with pytest.raises(ScenarioPlanError, match="ambiguous recorded"):
        store.find("robot", None, None)
    assert store.find("missing", None, None) is None
    (store.directory / "broken.json").write_text("not json")
    with pytest.raises(ScenarioExecutionError, match="cannot read scenario record"):
        store.records()


def test_injected_lifecycle_port_controls_container_restart(tmp_path: Path):
    from rigyard.scenarios.lifecycle import ContainerLifecycleBackend
    from rigyard.scenarios.runtime import ScenarioCommandGateway

    fake = FakeTmux()

    class NoRestart(ContainerLifecycleBackend):
        def restart(self, plan):
            pass

    backend = executor(fake, containers=NoRestart(ScenarioCommandGateway(fake)))
    backend.start(scenario_plan(instance()))
    assert not any(command[:2] == ("docker", "restart") for command in fake.commands)
