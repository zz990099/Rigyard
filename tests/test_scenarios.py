import io
from pathlib import Path

import pytest

from rigyard.application.requests import ResolutionRequest
from rigyard.application.scenarios import PlanScenarioUseCase
from rigyard.cli.main import run
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.config.loader import load_config
from rigyard.errors import (
    ResolutionError,
    ScenarioExecutionError,
    ScenarioPlanError,
    SchemaValidationError,
)
from rigyard.execution import CommandResult
from rigyard.scenarios.executor import PANE_GROUP_OPTION, ScenarioExecutor
from rigyard.scenarios.models import (
    ScenarioComposePlan,
    ScenarioGroupPlan,
    ScenarioInstancePlan,
    ScenarioPlan,
    ScenarioResult,
    ScenarioStartupPlan,
)
from rigyard.scenarios.process import (
    command_line,
    container_session_argv,
    host_shell_argv,
    keep_alive_argv,
    process_argv,
    startup_exit_code,
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
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: scenario-test}
sources: {scenarios: config/scenarios.yaml}
""",
    )
    write(tmp_path / "config/scenarios.yaml", scenarios)
    return config


def scenario_yaml() -> str:
    return """robot:
  description: Robot system
  instances:
    robot1:
      container: robot-dev
      groups:
        drivers:
          script: /ros2_ws/drivers.sh
          environment:
            ROS_DOMAIN_ID:
              default: "7"
              prompt: {mode: input, message: ROS domain}
        navigation:
          enabled: false
          script:
            prompt: {mode: input, message: Navigation script}
  profiles:
    development:
      attach: false
"""


def test_load_scenario_project_has_instances_and_groups(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    loaded = load_config(config)
    assert loaded.sources.scenarios == Path("config/scenarios.yaml")
    instance = loaded.scenarios["robot"].instances["robot1"]
    assert list(instance.groups) == ["drivers", "navigation"]
    assert instance.container == "robot-dev"
    assert set(loaded.scenarios["robot"].profiles) == {"development"}


def test_plan_is_lazy_across_profiles_instances_and_groups(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())

    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert isinstance(plan, ScenarioPlan)
    assert [instance.name for instance in plan.instances] == ["robot1"]
    groups = plan.instances[0].groups
    assert [group.name for group in groups] == ["drivers"]
    assert dict(groups[0].environment) == {"ROS_DOMAIN_ID": "7"}
    assert groups[0].script == "/ros2_ws/drivers.sh"
    assert plan.session.startswith("rigyard-scenario-test-robot-")
    assert plan.mouse is True


def test_plan_preserves_window_and_pane_startup_policies(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  startup: {mode: sequential, interval_seconds: 5}
  instances:
    robot1:
      container: robot-dev
      startup: {mode: sequential, interval_seconds: 2}
      groups:
        drivers: {script: /drivers.sh}
        navigation: {script: /navigation.sh}
  profiles:
    development: {attach: false}
""",
    )

    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert plan.startup == ScenarioStartupPlan("sequential", 5)
    assert plan.instances[0].startup == ScenarioStartupPlan("sequential", 2)


def test_startup_interval_must_be_in_the_supported_range(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  startup: {mode: sequential, interval_seconds: -1}
  instances:
    robot1: {container: robot-dev, groups: {drivers: {script: /drivers.sh}}}
  profiles:
    development: {attach: false}
""",
    )

    with pytest.raises(ResolutionError, match="greater than or equal to 0"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_plan_selects_requested_instances(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: container-a, groups: {drivers: {script: /a.sh}}}
    robot2: {container: container-b, groups: {drivers: {script: /b.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        instances=["robot2"],
    )
    assert isinstance(plan, ScenarioPlan)
    assert [instance.name for instance in plan.instances] == ["robot2"]
    assert plan.instances[0].container == "container-b"


def test_two_instances_plan_onto_two_containers(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: container-a
      groups: {drivers: {script: /a.sh}}
    robot2:
      container: container-b
      groups: {drivers: {script: /b.sh}}
  profiles:
    development: {attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )
    assert isinstance(plan, ScenarioPlan)
    assert [instance.container for instance in plan.instances] == ["container-a", "container-b"]


def test_compose_plan_uses_service_reference(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  compose:
    file: deploy/compose.yaml
    project_name: robot-debug
    wait_timeout_seconds: 30
  instances:
    robot1: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    compose_file = write(tmp_path / "deploy/compose.yaml", "services: {robot: {image: robot}}\n")

    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert isinstance(plan, ScenarioPlan)
    assert plan.compose == ScenarioComposePlan(compose_file.resolve(), "robot-debug", 30)
    assert plan.instances[0].service == "robot"
    assert plan.instances[0].container is None


def test_compose_environment_resolves_rigyard_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    config = project(
        tmp_path,
        """robot:
  compose:
    file: compose.yaml
    environment:
      WORKSPACE: ${WORKSPACE_ROOT}
      CONFIG_ROOT: ${RIGYARD_ROOT}
  instances:
    robot1: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    write(tmp_path / "compose.yaml", "services: {robot: {image: robot}}\n")

    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert isinstance(plan, ScenarioPlan)
    assert plan.compose is not None
    assert plan.compose.environment == (
        ("CONFIG_ROOT", str(tmp_path)),
        ("WORKSPACE", str(tmp_path)),
    )


def test_compose_plan_generates_a_stable_project_name(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  compose: {file: compose.yaml}
  instances:
    robot1: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    write(tmp_path / "compose.yaml", "services: {robot: {image: robot}}\n")

    first = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )
    second = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert isinstance(first, ScenarioPlan)
    assert isinstance(second, ScenarioPlan)
    assert first.compose is not None
    assert first.compose.project_name == second.compose.project_name
    assert first.compose.project_name.startswith("rigyard-scenario-test-robot-development-")


def test_compose_plan_rejects_a_missing_file(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  compose: {file: missing.yaml}
  instances:
    robot1: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(ScenarioPlanError, match="Compose file is not a file"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_unknown_instance_is_rejected(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    with pytest.raises(SchemaValidationError, match="unknown instance"):
        PlanScenarioUseCase().plan(
            "robot",
            "development",
            ResolutionRequest(config, interactive=False),
            instances=["nope"],
        )


def test_disabled_instance_cannot_be_selected(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: container-a, groups: {drivers: {script: /a.sh}}}
    robot2:
      enabled: false
      container: container-b
      groups: {drivers: {script: /b.sh}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="disabled"):
        PlanScenarioUseCase().plan(
            "robot",
            "development",
            ResolutionRequest(config, interactive=False),
            instances=["robot2"],
        )


def test_instance_container_supports_runtime_templates(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: "dev_${env:USER}"
      groups: {drivers: {script: /a.sh}}
  profiles:
    development: {attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        environment={"USER": "alice"},
    )
    assert isinstance(plan, ScenarioPlan)
    assert plan.instances[0].container == "dev_alice"


def test_instance_service_supports_runtime_templates(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  compose: {file: compose.yaml}
  instances:
    robot1:
      service: "${env:USER}-robot"
      groups: {drivers: {script: /a.sh}}
  profiles:
    development: {attach: false}
""",
    )
    write(tmp_path / "compose.yaml", "services: {alice-robot: {image: robot}}\n")

    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        environment={"USER": "alice"},
    )

    assert isinstance(plan, ScenarioPlan)
    assert plan.instances[0].service == "alice-robot"
    assert plan.instances[0].container is None


def test_scenario_instance_rejects_both_targets(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: robot-dev
      service: robot
      groups: {drivers: {script: /run.sh}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="exactly one"):
        load_config(config)


def test_scenario_instance_requires_container(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="container"):
        load_config(config)


@pytest.mark.parametrize(
    "legacy_field",
    (
        "      backend: tmux\n",
        "      compose_file: deploy/compose.yaml\n",
    ),
)
def test_scenario_profile_rejects_removed_backend_fields(tmp_path: Path, legacy_field: str):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: robot-dev, groups: {drivers: {script: /run.sh}}}
  profiles:
    development:
"""
        + legacy_field,
    )
    with pytest.raises(SchemaValidationError, match="Extra inputs are not permitted"):
        load_config(config)


@pytest.mark.parametrize(
    "legacy_field",
    (
        "      supervisor: {priority: 10}\n",
        "      groups: {drivers: {script: /run.sh, supervisor: {priority: 10}}}\n",
    ),
)
def test_scenario_rejects_removed_deployment_fields(tmp_path: Path, legacy_field: str):
    groups = "      groups: {drivers: {script: /run.sh}}\n"
    if "groups:" in legacy_field:
        groups = ""
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: robot-dev
"""
        + legacy_field
        + groups
        + "  profiles: {development: {attach: false}}\n",
    )
    with pytest.raises(SchemaValidationError, match="Extra inputs are not permitted"):
        load_config(config)


def test_non_compose_scenario_rejects_service_target(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {service: robot, groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="uses service"):
        load_config(config)


def test_compose_scenario_rejects_container_target(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  compose: {file: compose.yaml}
  instances:
    robot1: {container: robot, groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="uses container"):
        load_config(config)


def test_tmux_instance_name_must_be_a_target_safe_window_name(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot.1: {container: robot-dev, groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(ScenarioPlanError, match="invalid tmux window name"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_plan_defaults_to_the_only_configured_profile(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())

    plan = PlanScenarioUseCase().plan(
        "robot", None, ResolutionRequest(config, interactive=False)
    )

    assert plan.profile_name == "development"


def test_plan_requires_a_profile_when_several_are_configured(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: robot-dev, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
    headless: {attach: false}
""",
    )

    with pytest.raises(SchemaValidationError, match="needs a profile"):
        PlanScenarioUseCase().plan(
            "robot", None, ResolutionRequest(config, interactive=False)
        )


def test_cli_scene_start_defaults_to_the_only_profile(tmp_path: Path, capsys):
    config = project(tmp_path, scenario_yaml())

    assert (
        run(
            [
                "--config",
                str(config),
                "scene",
                "start",
                "robot",
                "--dry-run",
                "--non-interactive",
            ]
        )
        == 0
    )

    assert "Profile: development" in capsys.readouterr().out


def test_cli_scene_reports_an_ambiguous_profile_choice(tmp_path: Path, capsys):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: robot-dev, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
    headless: {attach: false}
""",
    )

    assert run(["--config", str(config), "scene", "stop", "robot", "--non-interactive"]) == 2

    assert "needs a profile" in capsys.readouterr().err


def test_management_plan_resolves_instance_container(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: {default: robot-dev, prompt: {mode: input, message: Container}}
      groups: {drivers: {script: /run.sh}}
  profiles:
    development: {attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        resolve_group_runtime=False,
    )
    assert isinstance(plan, ScenarioPlan)
    assert plan.instances[0].container == "robot-dev"
    assert [group.name for group in plan.instances[0].groups] == ["drivers"]


def test_group_requires_exactly_one_of_script_or_command(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: robot-dev
      groups: {drivers: {script: /run.sh, command: [/run.sh]}}
  profiles:
    development: {attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="exactly one of script or command"):
        load_config(config)


def test_schema_version_2_is_rejected_with_migration_hint(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        "version: 2\nmetadata: {name: old}\nsources: {scenarios: s.yaml}\n",
    )
    with pytest.raises(SchemaValidationError, match="instances.<name>"):
        load_config(config)


def group(
    name: str,
    *,
    script: str | None = None,
    command: tuple[str, ...] | None = None,
    setup: tuple[str, ...] = (),
    environment: tuple[tuple[str, str], ...] = (),
    workdir: str | None = "/ros2_ws",
) -> ScenarioGroupPlan:
    if script is None and command is None:
        script = f"/workspace/{name}.sh"
    return ScenarioGroupPlan(
        name=name,
        script=script,
        interpreter=("/bin/bash", "-euo", "pipefail"),
        user=None,
        workdir=workdir,
        environment=environment,
        command=command,
        setup=setup,
    )


def instance(
    name: str = "robot1",
    *,
    container: str | None = "robot-dev",
    service: str | None = None,
    groups: tuple[ScenarioGroupPlan, ...] = (),
    startup: ScenarioStartupPlan | None = None,
) -> ScenarioInstancePlan:
    if service is not None:
        container = None
    return ScenarioInstancePlan(
        name,
        container,
        groups or (group("drivers"),),
        service=service,
        startup=startup or ScenarioStartupPlan(),
    )


def scenario_plan(
    *instances: ScenarioInstancePlan,
    attach: bool = False,
    session: str = "robot-session",
    restart_container: str = "always",
    mouse: bool = True,
    partial: bool = False,
    keep_alive: bool = True,
    compose: ScenarioComposePlan | None = None,
    startup: ScenarioStartupPlan | None = None,
) -> ScenarioPlan:
    return ScenarioPlan(
        scene_name="robot",
        profile_name="development",
        session=session,
        attach=attach,
        replace=False,
        stop_grace_seconds=0,
        instances=instances or (instance(),),
        compose=compose,
        restart_container=restart_container,
        mouse=mouse,
        partial=partial,
        keep_alive=keep_alive,
        startup=startup or ScenarioStartupPlan(),
    )


def executor(fake, **kwargs) -> ScenarioExecutor:
    """Build an executor whose waits are instant so tests do not sleep."""

    return ScenarioExecutor(fake, sleep_fn=lambda _: None, **kwargs)


def split_target(target: str) -> tuple[str, int | None]:
    """Split a tmux 'session:window[.pane]' target into (window, pane index)."""

    _, _, rest = target.partition(":")
    window, _, pane = rest.partition(".")
    return window, int(pane) if pane else None


class FakeTmux:
    """In-memory tmux server plus the Docker calls the tmux backend makes."""

    def __init__(
        self,
        *,
        session: bool = False,
        windows: tuple[str, ...] = (),
        containers_running: bool = True,
        missing_containers: tuple[str, ...] = (),
        compose_services: tuple[str, ...] = ("robot",),
        compose_containers: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.session = session
        self.windows = list(windows)
        self.panes: dict[str, list[str]] = {name: [name] for name in windows}
        self.containers_running = containers_running
        self.missing = set(missing_containers)
        self.compose_services = compose_services
        self.compose_containers = compose_containers or {
            service: (f"{service}-container",) for service in compose_services
        }
        self.dead: dict[str, int] = {}
        self.pane_logs: dict[str, str] = {}
        self.calls: list[tuple[tuple[str, ...], dict]] = []
        self.override = None

    def run(self, command, **kwargs):
        command = tuple(command)
        self.calls.append((command, kwargs))
        if self.override is not None:
            outcome = self.override(command, kwargs)
            if outcome is not None:
                return outcome
        return self.handle(command)

    @property
    def commands(self) -> list[tuple[str, ...]]:
        return [command for command, _ in self.calls]

    def handle(self, command: tuple[str, ...]) -> CommandResult:
        if command[0] == "tmux":
            return self._tmux(command)
        if command[0] == "docker":
            return self._docker(command)
        return CommandResult(0)

    def _tmux(self, command: tuple[str, ...]) -> CommandResult:
        verb = command[1]
        target = command[command.index("-t") + 1] if "-t" in command else None
        if verb == "-V":
            return CommandResult(0, "tmux 3.2a\n")
        if verb == "has-session":
            return CommandResult(0 if self.session else 1)
        if verb in {"set-environment", "select-layout", "respawn-pane"}:
            return CommandResult(0)
        if verb == "set-option":
            if "-p" in command and PANE_GROUP_OPTION in command:
                name = command[command.index(PANE_GROUP_OPTION) + 1]
                window, pane = split_target(target or "")
                self.panes[window][pane or 0] = name
            return CommandResult(0)
        if verb == "new-session":
            name = command[command.index("-n") + 1]
            self.session = True
            self.windows = [name]
            self.panes = {name: [name]}
            return CommandResult(0)
        if verb == "new-window":
            name = command[command.index("-n") + 1]
            self.windows.append(name)
            self.panes[name] = [name]
            return CommandResult(0)
        if verb == "split-window":
            window, _ = split_target(target or "")
            self.panes[window].append(window)
            return CommandResult(0)
        if verb == "select-pane":
            # Titles are cosmetic; group lookup uses the pane option tag.
            return CommandResult(0)
        if verb == "select-window":
            return CommandResult(0)
        if verb == "kill-window":
            window, _ = split_target(target or "")
            self.windows = [name for name in self.windows if name != window]
            self.panes.pop(window, None)
            if not self.windows:
                self.session = False
            return CommandResult(0)
        if verb == "kill-session":
            self.session = False
            self.windows = []
            self.panes = {}
            return CommandResult(0)
        if verb == "list-windows":
            if not self.session:
                return CommandResult(1, stderr="can't find session\n")
            return CommandResult(0, "".join(f"{name}\n" for name in self.windows))
        if verb == "list-panes":
            if "-s" in command:
                lines = [
                    f"{window}.{index} {title} dead=0 exit="
                    for window in self.windows
                    for index, title in enumerate(self.panes[window])
                ]
                return CommandResult(0, "\n".join(lines) + "\n")
            window, _ = split_target(target or "")
            titles = self.panes.get(window)
            if titles is None:
                return CommandResult(1, stderr="no such window\n")
            return CommandResult(
                0, "\n".join(f"{title} {index}" for index, title in enumerate(titles)) + "\n"
            )
        if verb == "display-message":
            code = self.dead.get(target or "")
            if code is None:
                return CommandResult(0, "0 \n")
            return CommandResult(0, f"1 {code}\n")
        if verb == "capture-pane":
            return CommandResult(0, self.pane_logs.get(target or "", "pane output\n"))
        return CommandResult(0)

    def _docker(self, command: tuple[str, ...]) -> CommandResult:
        verb = command[1]
        if verb == "version":
            return CommandResult(0, "25.0.0\n")
        if verb == "inspect":
            name = command[-1]
            if name in self.missing:
                return CommandResult(1, stderr=f"Error: No such object: {name}\n")
            return CommandResult(0, "true\n" if self.containers_running else "false\n")
        if verb in {"restart", "start"}:
            self.containers_running = True
            return CommandResult(0)
        if verb == "compose":
            if command[2] == "version":
                return CommandResult(0, "Docker Compose version v2.30.0\n")
            if command[-2:] == ("config", "--services"):
                return CommandResult(0, "".join(f"{name}\n" for name in self.compose_services))
            if "ps" in command and "-q" in command:
                service = command[-1]
                ids = self.compose_containers.get(service, ())
                return CommandResult(0, "".join(f"{item}\n" for item in ids))
            return CommandResult(0)
        return CommandResult(0)


def test_group_command_and_setup_render_one_container_argv():
    item = group(
        "drivers",
        command=("ros2", "launch", "nhybot_bringup", "drivers.launch.py"),
        setup=("/opt/ros/humble/setup.bash", "install/setup.bash"),
    )
    expected = (
        "/bin/bash",
        "-euo",
        "pipefail",
        "-c",
        ". /opt/ros/humble/setup.bash && . install/setup.bash && exec "
        "ros2 launch nhybot_bringup drivers.launch.py",
    )
    assert process_argv(item) == expected


def test_group_script_form_still_renders_interpreter_and_script():
    assert process_argv(group("drivers")) == (
        "/bin/bash",
        "-euo",
        "pipefail",
        "/workspace/drivers.sh",
    )


def test_keep_alive_wrapper_survives_interrupts_and_hands_over_a_host_shell():
    primary = ("docker", "exec", "-it", "robot-dev", "bash", "-c", "sleep 1")
    argv = keep_alive_argv(primary, "drivers", ("/bin/bash", "-i"))
    assert argv[:2] == ("/bin/sh", "-c")
    program = argv[2]
    assert program.splitlines() == [
        'trap "" INT',
        "docker exec -it robot-dev bash -c 'sleep 1'",
        "__rigyard_status=$?",
        'echo "[rigyard] drivers container shell exited with code $__rigyard_status"',
        "trap - INT",
        "exec /bin/bash -i",
    ]


def test_container_session_runs_the_group_as_a_child_and_keeps_a_ready_shell():
    item = group(
        "drivers",
        command=("ros2", "launch", "a.launch.py"),
        setup=("install/setup.bash",),
    )

    argv = container_session_argv(item)

    assert argv[:4] == ("/bin/bash", "-euo", "pipefail", "-c")
    assert argv[-1].splitlines() == [
        ". install/setup.bash",
        "set +e",
        "ros2 launch a.launch.py",
        "__rigyard_status=$?",
        'echo "[rigyard] drivers exited with code $__rigyard_status"',
        '__rigyard_history="${HISTFILE-$HOME/.bash_history}"',
        'if [ -n "$__rigyard_history" ]; then',
        "  printf '%s\\n' '. install/setup.bash; ros2 launch a.launch.py'"
        ' >> "$__rigyard_history" 2>/dev/null',
        "fi",
        "exec /bin/bash -i",
    ]


def test_container_session_works_without_setup_and_for_scripts():
    assert container_session_argv(group("drivers", command=("true",)))[-1].splitlines() == [
        "set +e",
        "true",
        "__rigyard_status=$?",
        'echo "[rigyard] drivers exited with code $__rigyard_status"',
        '__rigyard_history="${HISTFILE-$HOME/.bash_history}"',
        'if [ -n "$__rigyard_history" ]; then',
        "  printf '%s\\n' true >> \"$__rigyard_history\" 2>/dev/null",
        "fi",
        "exec /bin/bash -i",
    ]
    assert container_session_argv(group("nav"))[-1].splitlines()[1:4] == [
        "/bin/bash -euo pipefail /workspace/nav.sh",
        "__rigyard_status=$?",
        'echo "[rigyard] nav exited with code $__rigyard_status"',
    ]


def test_command_line_matches_what_legacy_typed_into_the_pane():
    item = group(
        "drivers",
        command=("ros2", "launch", "a.launch.py", "use_sim_time:=True"),
        setup=("install/setup.bash",),
    )
    assert command_line(item) == (
        ". install/setup.bash; ros2 launch a.launch.py use_sim_time:=True"
    )
    assert command_line(group("nav")) == "/bin/bash -euo pipefail /workspace/nav.sh"


def test_host_shell_prefers_the_login_shell_and_falls_back_to_bash(tmp_path: Path):
    custom = tmp_path / "custom-shell"
    custom.write_text("#!/bin/sh\n")
    custom.chmod(0o755)

    assert host_shell_argv({"SHELL": str(custom)}) == (str(custom), "-i")
    assert host_shell_argv({"SHELL": "/does/not/exist"}) == ("/bin/bash", "-i")
    assert host_shell_argv({}) == ("/bin/bash", "-i")


def test_startup_exit_code_reads_the_keep_alive_marker():
    content = "boom\n[rigyard] drivers exited with code 127\n$ "
    assert startup_exit_code(content, "drivers") == 127
    assert startup_exit_code(content, "navigation") is None
    assert startup_exit_code("[rigyard] drivers exited with code ?\n", "drivers") is None


def test_tmux_start_creates_one_window_per_instance_and_one_pane_per_group():
    fake = FakeTmux()
    plan = scenario_plan(
        instance("robot1", groups=(group("drivers"), group("navigation"))),
        instance("robot2", container="container-b", groups=(group("application"),)),
    )
    result = executor(fake).start(plan)

    assert result.detail == "tmux:robot-session"
    assert fake.windows == ["robot1", "robot2"]
    assert fake.panes["robot1"] == ["drivers", "navigation"]
    assert fake.panes["robot2"] == ["application"]
    prefixes = [command[:2] for command in fake.commands]
    session = [command for command in fake.commands if command[:2] == ("tmux", "new-session")]
    assert len(session) == 1
    assert session[0][:7] == (
        "tmux",
        "new-session",
        "-d",
        "-s",
        "robot-session",
        "-n",
        "robot1",
    )
    assert prefixes.count(("tmux", "new-window")) == 1
    assert prefixes.count(("tmux", "split-window")) == 1
    assert prefixes.count(("tmux", "respawn-pane")) == 3
    assert all(
        command[-1] == "tiled"
        for command in fake.commands
        if command[:2] == ("tmux", "select-layout")
    )


def test_tmux_sequential_start_waits_only_between_panes_and_windows():
    fake = FakeTmux()
    waits: list[tuple[float, int, tuple[str, ...]]] = []

    def record_wait(seconds: float) -> None:
        started = sum(
            command[:2] == ("tmux", "respawn-pane") for command in fake.commands
        )
        waits.append((seconds, started, tuple(fake.windows)))

    plan = scenario_plan(
        instance(
            "robot1",
            groups=(group("drivers"), group("localization"), group("navigation")),
            startup=ScenarioStartupPlan("sequential", 2),
        ),
        instance("robot2", container="container-b", groups=(group("application"),)),
        startup=ScenarioStartupPlan("sequential", 5),
    )

    ScenarioExecutor(fake, sleep_fn=record_wait).start(plan)

    assert waits == [
        (2, 1, ("robot1",)),
        (2, 2, ("robot1",)),
        (5, 3, ("robot1",)),
        (0.4, 4, ("robot1", "robot2")),
    ]


def test_tmux_retiles_after_every_split_so_many_groups_fit():
    fake = FakeTmux()
    groups = tuple(group(f"group{index}", command=("true",)) for index in range(11))

    executor(fake).start(scenario_plan(instance(groups=groups), keep_alive=False))

    verbs = [command[1] for command in fake.commands if command[0] == "tmux"]
    assert verbs.count("split-window") == len(groups) - 1
    for index, verb in enumerate(verbs):
        if verb == "split-window":
            assert verbs[index + 1] == "select-layout"
    assert len(fake.panes["robot1"]) == len(groups)


def test_tmux_start_enables_mouse_and_pane_borders_by_default():
    fake = FakeTmux()
    executor(fake).start(scenario_plan(instance()))
    assert (
        "tmux",
        "set-option",
        "-t",
        "robot-session",
        "mouse",
        "on",
    ) in fake.commands
    window_options = [
        command for command in fake.commands if command[:3] == ("tmux", "set-option", "-w")
    ]
    assert ("pane-border-status", "top") in [
        (command[-2], command[-1]) for command in window_options
    ]
    assert any(
        command[-2:] == ("pane-border-format", "#{pane_index}: #{@rigyard_group}")
        for command in window_options
    )
    remain = [command for command in window_options if "remain-on-exit" in command]
    assert remain and all(command[-2:] == ("remain-on-exit", "on") for command in remain)


def test_tmux_start_can_disable_mouse():
    fake = FakeTmux()
    executor(fake).start(scenario_plan(instance(), mouse=False))
    assert ("tmux", "set-option", "-t", "robot-session", "mouse", "off") in fake.commands


def test_tmux_start_restarts_every_instance_container():
    fake = FakeTmux()
    plan = scenario_plan(
        instance("robot1", container="container-a"),
        instance("robot2", container="container-b"),
    )
    executor(fake).start(plan)
    assert ("docker", "restart", "container-a") in fake.commands
    assert ("docker", "restart", "container-b") in fake.commands


def test_compose_start_resolves_services_before_creating_tmux_windows(tmp_path: Path):
    fake = FakeTmux(compose_services=("robot", "simulator"))
    plan = scenario_plan(
        instance("robot1", service="robot"),
        instance("sim", service="simulator"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 45),
    )

    executor(fake).start(plan)

    base = (
        "docker",
        "compose",
        "-f",
        str(tmp_path / "compose.yaml"),
        "--project-name",
        "robot-debug",
    )
    down = (*base, "down", "--remove-orphans")
    up = (*base, "up", "-d", "--wait", "--wait-timeout", "45", "robot", "simulator")
    assert down in fake.commands
    assert up in fake.commands
    assert fake.commands.index(down) < fake.commands.index(up) < next(
        index
        for index, command in enumerate(fake.commands)
        if command[:2] == ("tmux", "new-session")
    )
    pane_commands = [
        command for command in fake.commands if command[:2] == ("tmux", "respawn-pane")
    ]
    assert any("robot-container" in " ".join(command) for command in pane_commands)
    assert any("simulator-container" in " ".join(command) for command in pane_commands)
    assert not any(command[:2] == ("docker", "restart") for command in fake.commands)


def test_compose_start_stops_tmux_before_recreating_project(tmp_path: Path):
    fake = FakeTmux(session=True, windows=("robot1",))
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
    )

    executor(fake).start(plan)

    base = (
        "docker",
        "compose",
        "-f",
        str(tmp_path / "compose.yaml"),
        "--project-name",
        "robot-debug",
    )
    kill = ("tmux", "kill-session", "-t", "robot-session")
    down = (*base, "down", "--remove-orphans")
    up = (*base, "up", "-d", "--wait", "--wait-timeout", "60", "robot")
    assert fake.commands.index(kill) < fake.commands.index(down) < fake.commands.index(up)


def test_compose_start_aborts_when_previous_project_cannot_be_removed(tmp_path: Path):
    fake = FakeTmux()

    def fail_down(command, _):
        if command[:2] == ("docker", "compose") and "down" in command:
            return CommandResult(17, stderr="resource is busy")
        return None

    fake.override = fail_down
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
    )

    with pytest.raises(
        ScenarioExecutionError, match="Docker Compose down failed.*resource is busy"
    ):
        executor(fake).start(plan)

    assert not any(
        command[:2] == ("docker", "compose") and "up" in command
        for command in fake.commands
    )
    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


def test_partial_compose_start_preserves_the_existing_project(tmp_path: Path):
    fake = FakeTmux(session=True, windows=("other",), compose_services=("robot", "other"))
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
        partial=True,
    )

    executor(fake).start(plan)

    assert not any(
        command[:2] == ("docker", "compose") and "down" in command
        for command in fake.commands
    )
    assert any(
        command[:2] == ("docker", "compose") and "up" in command
        for command in fake.commands
    )
    assert "other" in fake.windows


def test_compose_commands_receive_resolved_environment(tmp_path: Path):
    fake = FakeTmux()
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(
            tmp_path / "compose.yaml",
            "robot-debug",
            60,
            (("WORKSPACE", "/resolved/workspace"),),
        ),
    )

    executor(
        fake,
        environment={"PATH": "/usr/bin", "WORKSPACE": "/host/workspace", "HOST_ONLY": "yes"},
    ).start(plan)

    compose_calls = [
        (command, kwargs)
        for command, kwargs in fake.calls
        if command[:2] == ("docker", "compose") and command[2] != "version"
    ]
    assert compose_calls
    for _, kwargs in compose_calls:
        assert kwargs["environment"] == {
            "PATH": "/usr/bin",
            "WORKSPACE": "/resolved/workspace",
            "HOST_ONLY": "yes",
        }


def test_compose_start_rejects_unknown_services_before_up(tmp_path: Path):
    fake = FakeTmux(compose_services=("other",))
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
    )

    with pytest.raises(ScenarioPlanError, match="unknown Compose service.*robot"):
        executor(fake).start(plan)

    assert not any("up" in command for command in fake.commands)
    assert not any("down" in command for command in fake.commands)
    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


def test_compose_start_requires_one_container_per_service(tmp_path: Path):
    fake = FakeTmux(compose_containers={"robot": ("one", "two")})
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
    )

    with pytest.raises(ScenarioExecutionError, match="exactly one container"):
        executor(fake).start(plan)

    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


def test_compose_down_stops_tmux_then_removes_environment(tmp_path: Path):
    fake = FakeTmux(session=True, windows=("robot1",))
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
    )

    result = executor(fake).down(plan)

    down = (
        "docker",
        "compose",
        "-f",
        str(tmp_path / "compose.yaml"),
        "--project-name",
        "robot-debug",
        "down",
        "--remove-orphans",
    )
    kill = ("tmux", "kill-session", "-t", "robot-session")
    assert result.detail == "down"
    assert fake.commands.index(kill) < fake.commands.index(down)


def test_compose_down_rejects_existing_container_scenarios():
    with pytest.raises(ScenarioPlanError, match="only available for Compose-managed"):
        executor(FakeTmux()).down(scenario_plan(instance()))


def test_compose_down_rejects_partial_selection(tmp_path: Path):
    plan = scenario_plan(
        instance(service="robot"),
        compose=ScenarioComposePlan(tmp_path / "compose.yaml", "robot-debug", 60),
        partial=True,
    )
    with pytest.raises(ScenarioPlanError, match="does not support partial"):
        executor(FakeTmux()).down(plan)


def test_tmux_replaces_the_session_before_restarting_containers():
    fake = FakeTmux(session=True, windows=("robot1",))
    executor(fake).start(scenario_plan(instance()))
    commands = [command for command, _ in fake.calls]
    assert (
        commands.index(("tmux", "kill-session", "-t", "robot-session"))
        < commands.index(("docker", "restart", "robot-dev"))
        < next(
            index
            for index, command in enumerate(commands)
            if command[:2] == ("tmux", "new-session")
        )
    )


def test_tmux_start_replaces_a_session_left_over_from_another_layout():
    # A session owned by this scenario may still hold windows the new layout does not know about.
    fake = FakeTmux(session=True, windows=("drivers", "navigation"))
    result = executor(fake).start(scenario_plan(instance()))
    assert result.detail == "tmux:robot-session"
    assert fake.windows == ["robot1"]
    created = next(command for command in fake.commands if command[:2] == ("tmux", "new-session"))
    assert created[:7] == (
        "tmux",
        "new-session",
        "-d",
        "-s",
        "robot-session",
        "-n",
        "robot1",
    )


def test_partial_start_joins_an_existing_session():
    fake = FakeTmux(session=True, windows=("robot2",))
    plan = scenario_plan(instance("robot1"), partial=True)
    executor(fake).start(plan)
    assert fake.windows == ["robot2", "robot1"]
    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


@pytest.mark.parametrize("policy", ["if_not_running", "never"])
def test_tmux_restart_policy_can_leave_a_running_container_alone(policy: str):
    fake = FakeTmux()
    executor(fake).start(scenario_plan(instance(), restart_container=policy))
    assert not any(
        command[:2] in {("docker", "restart"), ("docker", "start")} for command in fake.commands
    )


def test_tmux_restart_policy_if_not_running_starts_a_stopped_container():
    fake = FakeTmux(containers_running=False)
    executor(fake).start(scenario_plan(instance(), restart_container="if_not_running"))
    assert ("docker", "start", "robot-dev") in fake.commands
    assert not any(command[:2] == ("docker", "restart") for command in fake.commands)


def test_tmux_missing_container_reports_an_actionable_error():
    fake = FakeTmux(missing_containers=("robot-dev",))
    with pytest.raises(ScenarioExecutionError, match="rigyard container create robot-dev"):
        executor(fake).start(scenario_plan(instance()))


def test_tmux_partial_start_failure_cleans_new_session():
    fake = FakeTmux()

    def override(command, _):
        if command[:2] == ("tmux", "new-window"):
            return CommandResult(9, stderr="failed")
        return None

    fake.override = override
    plan = scenario_plan(instance("robot1"), instance("robot2", container="container-b"))
    with pytest.raises(ScenarioExecutionError, match="cannot create tmux window"):
        executor(fake).start(plan)
    assert ("tmux", "kill-session", "-t", "robot-session") in fake.commands
    assert fake.session is False


def test_tmux_uses_direct_arguments_and_refreshes_stale_docker_environment():
    fake = FakeTmux()
    item = instance(groups=(group("drivers", script="/workspace/a script.sh"),))
    executor(
        fake,
        environment={"PATH": "/usr/bin", "DOCKER_HOST": "tcp://host:2375"},
    ).start(scenario_plan(item, keep_alive=False))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    assert process[5:8] == ("docker", "exec", "-it")
    assert process[-1] == "/workspace/a script.sh"
    assert (
        "tmux",
        "set-environment",
        "-t",
        "robot-session",
        "DOCKER_HOST",
        "tcp://host:2375",
    ) in fake.commands
    assert (
        "tmux",
        "set-environment",
        "-t",
        "robot-session",
        "-r",
        "DOCKER_CONTEXT",
    ) in fake.commands


def test_tmux_window_runs_group_command_with_setup():
    item = instance(
        groups=(
            group(
                "drivers",
                command=("ros2", "launch", "a.launch.py"),
                setup=("install/setup.bash",),
            ),
        )
    )
    fake = FakeTmux()
    executor(fake).start(scenario_plan(item, keep_alive=False))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    expected = (
        "/bin/bash",
        "-euo",
        "pipefail",
        "-c",
        ". install/setup.bash && exec ros2 launch a.launch.py",
    )
    assert process[5:7] == ("docker", "exec")
    assert process[-len(expected) :] == expected


def test_tmux_keep_alive_pane_keeps_a_ready_container_shell_and_a_host_terminal():
    fake = FakeTmux()
    executor(fake, environment={"SHELL": "/bin/bash"}).start(scenario_plan(instance()))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    assert process[5:7] == ("/bin/sh", "-c")
    program = process[-1]
    assert program.startswith('trap "" INT\ndocker exec -it')
    # The group runs as a child, then leaves an interactive container shell with setup sourced.
    assert "set +e\n/bin/bash -euo pipefail /workspace/drivers.sh" in program
    assert "[rigyard] drivers exited with code $__rigyard_status" in program
    assert "exec /bin/bash -i" in program
    # After the container shell exits, reset SIGINT and enter a host shell to keep the pane usable.
    assert "[rigyard] drivers container shell exited with code $__rigyard_status" in program
    assert program.endswith("trap - INT\nexec /bin/bash -i")


def test_tmux_keep_alive_pane_sources_group_setup_before_the_ready_shell():
    item = instance(
        groups=(
            group(
                "drivers",
                command=("ros2", "launch", "a.launch.py"),
                setup=("install/setup.bash",),
            ),
        )
    )
    fake = FakeTmux()
    executor(fake).start(scenario_plan(item))
    program = next(
        command for command in fake.commands if command[:2] == ("tmux", "respawn-pane")
    )[-1]
    assert ". install/setup.bash\nset +e\nros2 launch a.launch.py" in program


def test_tmux_reports_a_group_that_exited_before_keep_alive_shell_started():
    fake = FakeTmux()
    fake.pane_logs["robot-session:robot1.0"] = (
        "docker: Error response from daemon: No such file\n"
        "[rigyard] drivers exited with code 127\n"
        "root@container:/ros2_ws# "
    )
    with pytest.raises(ScenarioExecutionError, match="exit 127.*No such file"):
        executor(fake).start(scenario_plan(instance()))


def test_tmux_keep_alive_can_be_disabled():
    fake = FakeTmux()
    executor(fake).start(scenario_plan(instance(), keep_alive=False))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    assert process[-1] == "/workspace/drivers.sh"
    assert not any(command[:2] == ("tmux", "capture-pane") for command in fake.commands)


def test_tmux_reports_dead_pane_and_keeps_failure_logs():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.dead["robot-session:robot1.0"] = 127
    fake.pane_logs["robot-session:robot1.0"] = "docker: command not found\n"
    with pytest.raises(ScenarioExecutionError, match="exit 127.*docker: command not found"):
        executor(fake).start(scenario_plan(instance()))
    assert fake.session is True


def test_tmux_stop_interrupts_every_pane_then_kills_the_session():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    tmux_backend = executor(fake)

    plan = scenario_plan(instance(groups=(group("drivers"), group("navigation"))))
    assert tmux_backend.stop(plan).detail == "stopped"
    interrupts = [command for command in fake.commands if command[:2] == ("tmux", "send-keys")]
    assert [command[-2] for command in interrupts] == [
        "robot-session:robot1.0",
        "robot-session:robot1.1",
    ]
    assert fake.commands[-1] == ("tmux", "kill-session", "-t", "robot-session")
    assert fake.session is False


def test_partial_stop_only_touches_selected_instances():
    fake = FakeTmux(session=True, windows=("robot1", "robot2"))
    plan = scenario_plan(instance("robot2", container="container-b"), partial=True)
    executor(fake).stop(plan)
    assert ("tmux", "kill-window", "-t", "robot-session:robot2") in fake.commands
    assert ("tmux", "kill-window", "-t", "robot-session:robot1") not in fake.commands
    assert fake.windows == ["robot1"]


def test_tmux_logs_requires_an_instance_when_several_are_running():
    fake = FakeTmux(session=True, windows=("robot1", "robot2"))
    plan = scenario_plan(instance("robot1"), instance("robot2", container="container-b"))
    with pytest.raises(ScenarioPlanError, match="select one with --instance"):
        executor(fake).logs(plan, None, "drivers")


def test_tmux_logs_captures_the_named_group_pane():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    fake.pane_logs["robot-session:robot1.1"] = "navigation log\n"
    plan = scenario_plan(instance(groups=(group("drivers"), group("navigation"))))
    result = executor(fake).logs(plan, "robot1", "navigation")
    assert result.detail == "navigation log"
    assert (
        "tmux",
        "capture-pane",
        "-p",
        "-t",
        "robot-session:robot1.1",
        "-S",
        "-",
    ) in fake.commands


def test_tmux_logs_follows_by_attaching():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers"]
    plan = scenario_plan(instance())
    executor(fake).logs(plan, "robot1", "drivers", follow=True)
    assert ("tmux", "attach-session", "-t", "robot-session") in fake.commands


def test_tmux_attach_selects_the_instance_window_and_group_pane():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    plan = scenario_plan(instance(groups=(group("drivers"), group("navigation"))))
    result = executor(fake).attach(plan, "robot1", "navigation")
    assert result.detail == "detached from robot-session:robot1.1"
    assert ("tmux", "select-window", "-t", "robot-session:robot1") in fake.commands
    assert ("tmux", "select-pane", "-t", "robot-session:robot1.1") in fake.commands


def test_tmux_status_lists_windows_and_panes():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    result = executor(fake).status(scenario_plan(instance()))
    assert "robot1.0 drivers" in result.detail
    assert "robot1.1 navigation" in result.detail


def test_tmux_status_reports_a_missing_session():
    fake = FakeTmux()
    assert executor(fake).status(scenario_plan(instance())).detail == "not running"


def test_cli_dry_run_describes_existing_container_runtime(tmp_path: Path, capsys):
    config = project(tmp_path, scenario_yaml())
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
                "--no-attach",
                "--non-interactive",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Runtime: tmux in existing containers" in output
    assert "Instances: robot1" in output
    assert "Window robot1: container=robot-dev -> drivers" in output
    assert "Window startup: parallel" in output
    assert "Pane startup robot1: parallel" in output
    assert "Mouse mode: on" in output
    assert "Container restart: always" in output


def test_cli_dry_run_selects_one_instance(tmp_path: Path, capsys):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: container-a, groups: {drivers: {script: /a.sh}}}
    robot2: {container: container-b, groups: {drivers: {script: /b.sh}}}
  profiles:
    development: {attach: false}
""",
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
                "--instance",
                "robot2",
                "--dry-run",
                "--non-interactive",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Instances: robot2" in output
    assert "Window robot2: container=container-b -> drivers" in output


def test_cli_dry_run_describes_compose_runtime(tmp_path: Path, capsys):
    config = project(
        tmp_path,
        """robot:
  compose:
    file: compose.yaml
    project_name: robot-debug
    wait_timeout_seconds: 20
    environment: {WORKSPACE: /workspace}
  instances:
    robot1: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    compose_file = write(tmp_path / "compose.yaml", "services: {robot: {image: robot}}\n")

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
                "--non-interactive",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Runtime: tmux in Compose-managed containers" in output
    assert f"Compose file: {compose_file.resolve()}" in output
    assert "Compose project: robot-debug" in output
    assert "Compose start: recreate project" in output
    assert "Compose wait timeout: 20s" in output
    assert "Compose environment keys: WORKSPACE" in output
    assert "Window robot1: service=robot -> drivers" in output
    assert "/workspace" not in output
    assert "Container restart:" not in output


class FakeScenarioExecutor:
    def __init__(self) -> None:
        self.started = []
        self.stopped = []
        self.downed = []

    def start(self, plan):
        self.started.append(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name)

    def stop(self, plan):
        self.stopped.append(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name)

    def down(self, plan):
        self.downed.append(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name, "down")


def test_menu_starts_scene_once_and_exits(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    executor = FakeScenarioExecutor()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n1\n1\n\ny\n"), output),
        scenario_executor_factory=lambda: executor,
    )
    assert app.run(config) == 0
    assert len(executor.started) == 1
    rendered = output.getvalue()
    assert rendered.count("Configuration:") == 1
    assert "Select profile" not in rendered  # A single profile is selected without prompting.
    assert "Profile: development" in rendered
    assert "Started scenario 'robot' profile 'development'" in rendered


def test_menu_groups_scenarios_by_source_description(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: menu-scenarios}
sources:
  scenarios:
    - scenarios/a.yaml
    - scenarios/b.yaml
""",
    )
    write(
        tmp_path / "scenarios/a.yaml",
        """description: A scenarios
scene-a:
  description: Scene A
  instances:
    robot1: {container: container-a, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    write(
        tmp_path / "scenarios/b.yaml",
        """description: B scenarios
scene-b:
  description: Scene B
  instances:
    robot1: {container: container-b, groups: {drivers: {script: /b.sh}}}
  profiles:
    development: {attach: false}
""",
    )

    executor = FakeScenarioExecutor()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n1\n2\n1\ny\n"), output),
        scenario_executor_factory=lambda: executor,
    )

    assert app.run(config) == 0
    assert len(executor.started) == 1
    assert executor.started[0].scene_name == "scene-b"
    rendered = output.getvalue()
    assert "1) A scenarios (scenarios/a.yaml)" in rendered
    assert "2) B scenarios (scenarios/b.yaml)" in rendered


def test_menu_scene_submenu_lists_start_stop_and_down(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n0\n0\n"), output),
        scenario_executor_factory=lambda: FakeScenarioExecutor(),
    )

    assert app.run(config) == 0

    rendered = output.getvalue()
    assert "1) Start scene" in rendered
    assert "2) Stop scene" in rendered
    assert "3) Down scene" in rendered


def test_menu_asks_for_the_profile_when_several_are_configured(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: robot-dev, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
    headless: {attach: false}
""",
    )
    executor = FakeScenarioExecutor()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n1\n1\n2\ny\n"), output),
        scenario_executor_factory=lambda: executor,
    )

    assert app.run(config) == 0

    rendered = output.getvalue()
    assert "1) development" in rendered
    assert "2) headless" in rendered
    assert "Profile: headless" in rendered


def test_menu_stop_scene_stops_and_reports(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    executor = FakeScenarioExecutor()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n2\n1\ny\n"), output),
        scenario_executor_factory=lambda: executor,
    )

    assert app.run(config) == 0

    assert len(executor.stopped) == 1
    assert executor.stopped[0].scene_name == "robot"
    rendered = output.getvalue()
    assert "Stop this scenario now?" in rendered
    assert "Scenario 'robot': stopped" in rendered


def test_menu_down_scene_is_unavailable_without_compose_scenes(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n3\n"), output),
        scenario_executor_factory=lambda: FakeScenarioExecutor(),
    )

    assert app.run(config) == 2

    assert "no Compose-managed scenes configured" in output.getvalue()


def test_menu_down_scene_removes_the_compose_environment(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: menu-compose}
sources: {scenarios: scenarios/compose.yaml}
""",
    )
    write(tmp_path / "deploy.yaml", "services: {robot: {image: ubuntu}}\n")
    write(
        tmp_path / "scenarios/compose.yaml",
        """compose-scene:
  compose: {file: deploy.yaml, project_name: menu-compose-project}
  instances:
    robot: {service: robot, groups: {drivers: {script: /a.sh}}}
  profiles:
    development: {attach: false}
""",
    )
    executor = FakeScenarioExecutor()
    output = TTYBuffer()
    app = MenuApp(
        MenuIO(TTYBuffer("4\n3\n1\ny\n"), output),
        scenario_executor_factory=lambda: executor,
    )

    assert app.run(config) == 0

    assert len(executor.downed) == 1
    assert executor.downed[0].scene_name == "compose-scene"
    assert "Scenario 'compose-scene': down" in output.getvalue()


def test_tmux_runner_os_error_is_actionable():
    class Broken:
        def run(self, *_args, **_kwargs):
            raise FileNotFoundError("missing")

    with pytest.raises(Exception, match="cannot execute tmux"):
        ScenarioExecutor(Broken()).start(scenario_plan(instance()))
