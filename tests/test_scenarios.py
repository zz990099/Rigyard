import io
import shlex
from dataclasses import replace
from pathlib import Path

import pytest

from toolchain.application.requests import ResolutionRequest
from toolchain.application.scenarios import PlanScenarioUseCase
from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.config.loader import load_config
from toolchain.errors import ScenarioExecutionError, ScenarioPlanError, SchemaValidationError
from toolchain.execution import CommandResult
from toolchain.providers.supervisor import ComposeSupervisorBackend, render_supervisor_config
from toolchain.providers.tmux import TmuxScenarioBackend
from toolchain.providers.tmux.backend import PANE_GROUP_OPTION
from toolchain.scenarios.models import (
    ComposeSupervisorPlan,
    ScenarioGroupPlan,
    ScenarioInstancePlan,
    ScenarioResult,
    SupervisorOptionsSpec,
    TmuxScenarioPlan,
)
from toolchain.scenarios.process import keep_alive_argv, process_argv, startup_exit_code


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
        """version: 3
metadata: {name: scenario-test}
sources: {scenarios: config/scenarios.yaml}
""",
    )
    write(tmp_path / "config/scenarios.yaml", scenarios)
    return config


def scenario_yaml(compose_file: str = "deploy/compose.yaml") -> str:
    return f"""robot:
  description: Robot system
  instances:
    robot1:
      container: robot-dev
      service: robot
      groups:
        drivers:
          script: /ros2_ws/drivers.sh
          environment:
            ROS_DOMAIN_ID:
              default: "7"
              prompt: {{mode: input, message: ROS domain}}
        navigation:
          enabled: false
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


def test_load_scenario_project_has_instances_and_groups(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())
    loaded = load_config(config)
    assert loaded.sources.scenarios == Path("config/scenarios.yaml")
    instance = loaded.scenarios["robot"].instances["robot1"]
    assert list(instance.groups) == ["drivers", "navigation"]
    assert instance.container == "robot-dev"
    assert set(loaded.scenarios["robot"].profiles) == {"development", "deployment"}


def test_plan_is_lazy_across_profiles_instances_and_groups(tmp_path: Path):
    config = project(tmp_path, scenario_yaml())

    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )

    assert isinstance(plan, TmuxScenarioPlan)
    assert [instance.name for instance in plan.instances] == ["robot1"]
    groups = plan.instances[0].groups
    assert [group.name for group in groups] == ["drivers"]
    assert dict(groups[0].environment) == {"ROS_DOMAIN_ID": "7"}
    assert groups[0].script == "/ros2_ws/drivers.sh"
    assert plan.session.startswith("tc-scenario-test-robot-")
    assert plan.mouse is True


def test_plan_selects_requested_instances(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {container: container-a, groups: {drivers: {script: /a.sh}}}
    robot2: {container: container-b, groups: {drivers: {script: /b.sh}}}
  profiles:
    development: {backend: tmux, attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        instances=["robot2"],
    )
    assert isinstance(plan, TmuxScenarioPlan)
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
    development: {backend: tmux, attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(config, interactive=False)
    )
    assert isinstance(plan, TmuxScenarioPlan)
    assert [instance.container for instance in plan.instances] == ["container-a", "container-b"]


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
    development: {backend: tmux, attach: false}
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
    development: {backend: tmux, attach: false}
""",
    )
    plan = PlanScenarioUseCase().plan(
        "robot",
        "development",
        ResolutionRequest(config, interactive=False),
        environment={"USER": "alice"},
    )
    assert isinstance(plan, TmuxScenarioPlan)
    assert plan.instances[0].container == "dev_alice"


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
    assert [(item.name, item.service) for item in plan.instances] == [("robot1", "robot")]


def test_tmux_instance_requires_container(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1: {groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {backend: tmux, attach: false}
""",
    )
    with pytest.raises(ScenarioPlanError, match="requires container for instance"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_tmux_instance_name_must_be_a_target_safe_window_name(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot.1: {container: robot-dev, groups: {drivers: {script: /run.sh}}}
  profiles:
    development: {backend: tmux, attach: false}
""",
    )
    with pytest.raises(ScenarioPlanError, match="invalid tmux window name"):
        PlanScenarioUseCase().plan(
            "robot", "development", ResolutionRequest(config, interactive=False)
        )


def test_management_plan_does_not_require_instance_container(tmp_path: Path):
    config = project(
        tmp_path,
        """robot:
  instances:
    robot1:
      container: {prompt: {mode: input, message: Container}}
      groups: {drivers: {script: /run.sh}}
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
    development: {backend: tmux, attach: false}
""",
    )
    with pytest.raises(SchemaValidationError, match="exactly one of script or command"):
        load_config(config)


def test_schema_version_2_is_rejected_with_migration_hint(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
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
        supervisor=SupervisorOptionsSpec(),
        command=command,
        setup=setup,
    )


def instance(
    name: str = "robot1",
    *,
    container: str | None = "robot-dev",
    service: str | None = "robot",
    groups: tuple[ScenarioGroupPlan, ...] = (),
) -> ScenarioInstancePlan:
    return ScenarioInstancePlan(name, container, service, groups or (group("drivers"),))


def tmux_plan(
    *instances: ScenarioInstancePlan,
    attach: bool = False,
    session: str = "robot-session",
    restart_container: str = "always",
    mouse: bool = True,
    compose_file: Path | None = None,
    project_name: str | None = None,
    partial: bool = False,
    keep_alive: bool = True,
) -> TmuxScenarioPlan:
    return TmuxScenarioPlan(
        scene_name="robot",
        profile_name="development",
        session=session,
        attach=attach,
        replace=False,
        stop_grace_seconds=0,
        instances=instances or (instance(),),
        compose_file=compose_file,
        project_name=project_name,
        restart_container=restart_container,
        mouse=mouse,
        partial=partial,
        keep_alive=keep_alive,
    )


def backend(fake, **kwargs) -> TmuxScenarioBackend:
    """Build a tmux backend whose waits are instant so tests do not sleep."""

    return TmuxScenarioBackend(fake, sleep_fn=lambda _: None, **kwargs)


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
    ) -> None:
        self.session = session
        self.windows = list(windows)
        self.panes: dict[str, list[str]] = {name: [name] for name in windows}
        self.containers_running = containers_running
        self.missing = set(missing_containers)
        self.compose_services = compose_services
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
            if "version" in command:
                return CommandResult(0, "Docker Compose version v2.24.0\n")
            if command[-2:] == ("config", "--services"):
                return CommandResult(0, "".join(f"{name}\n" for name in self.compose_services))
            if "ps" in command:
                return CommandResult(0, f"{command[-1]}-container\n")
            return CommandResult(0)
        return CommandResult(0)


def test_group_command_and_setup_render_one_argv_for_every_backend():
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
    assert f"command={shlex.join(expected)}" in render_supervisor_config((item,))


def test_group_script_form_still_renders_interpreter_and_script():
    assert process_argv(group("drivers")) == (
        "/bin/bash",
        "-euo",
        "pipefail",
        "/workspace/drivers.sh",
    )


def test_keep_alive_wrapper_survives_interrupts_and_hands_over_a_shell():
    primary = ("docker", "exec", "-it", "robot-dev", "bash", "-c", "sleep 1")
    fallback = ("docker", "exec", "-it", "robot-dev", "bash", "-i")
    argv = keep_alive_argv(primary, fallback, "drivers")
    assert argv[:2] == ("/bin/sh", "-c")
    program = argv[2]
    assert program.splitlines() == [
        'trap "" INT',
        "docker exec -it robot-dev bash -c 'sleep 1'",
        "__toolchain_status=$?",
        'echo "[toolchain] drivers exited with code $__toolchain_status"',
        "docker exec -it robot-dev bash -i",
    ]


def test_startup_exit_code_reads_the_keep_alive_marker():
    content = "boom\n[toolchain] drivers exited with code 127\n$ "
    assert startup_exit_code(content, "drivers") == 127
    assert startup_exit_code(content, "navigation") is None
    assert startup_exit_code("[toolchain] drivers exited with code ?\n", "drivers") is None


def test_supervisor_renderer_has_ros_friendly_shutdown_and_escaped_environment():
    item = group(
        "navigation",
        script="/workspace/nav%2.sh",
        environment=(("VALUE", 'a%b"c'),),
    )
    item = replace(item, supervisor=SupervisorOptionsSpec(priority=20, stopwaitsecs=30))
    rendered = render_supervisor_config((item,))
    assert "[program:navigation]" in rendered
    assert "nav%%2.sh" in rendered
    assert "stopsignal=INT" in rendered
    assert "stopasgroup=true" in rendered
    assert "killasgroup=true" in rendered
    assert 'environment=VALUE="a%%b\\"c"' in rendered
    assert "stdout_logfile=/dev/fd/1" in rendered


def test_tmux_start_creates_one_window_per_instance_and_one_pane_per_group():
    fake = FakeTmux()
    plan = tmux_plan(
        instance("robot1", groups=(group("drivers"), group("navigation"))),
        instance("robot2", container="container-b", groups=(group("application"),)),
    )
    result = backend(fake).start(plan)

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


def test_tmux_start_enables_mouse_and_pane_borders_by_default():
    fake = FakeTmux()
    backend(fake).start(tmux_plan(instance()))
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
        command[-2:] == ("pane-border-format", "#{pane_index}: #{@tc_group}")
        for command in window_options
    )
    remain = [command for command in window_options if "remain-on-exit" in command]
    assert remain and all(command[-2:] == ("remain-on-exit", "on") for command in remain)


def test_tmux_start_can_disable_mouse():
    fake = FakeTmux()
    backend(fake).start(tmux_plan(instance(), mouse=False))
    assert ("tmux", "set-option", "-t", "robot-session", "mouse", "off") in fake.commands


def test_tmux_start_restarts_every_instance_container():
    fake = FakeTmux()
    plan = tmux_plan(
        instance("robot1", container="container-a"),
        instance("robot2", container="container-b"),
    )
    backend(fake).start(plan)
    assert ("docker", "restart", "container-a") in fake.commands
    assert ("docker", "restart", "container-b") in fake.commands


def test_tmux_replaces_the_session_before_restarting_containers():
    fake = FakeTmux(session=True, windows=("robot1",))
    backend(fake).start(tmux_plan(instance()))
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
    result = backend(fake).start(tmux_plan(instance()))
    assert result.detail == "tmux:robot-session"
    assert fake.windows == ["robot1"]
    created = next(
        command for command in fake.commands if command[:2] == ("tmux", "new-session")
    )
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
    plan = tmux_plan(instance("robot1"), partial=True)
    backend(fake).start(plan)
    assert fake.windows == ["robot2", "robot1"]
    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


@pytest.mark.parametrize("policy", ["if_not_running", "never"])
def test_tmux_restart_policy_can_leave_a_running_container_alone(policy: str):
    fake = FakeTmux()
    backend(fake).start(tmux_plan(instance(), restart_container=policy))
    assert not any(
        command[:2] in {("docker", "restart"), ("docker", "start")}
        for command in fake.commands
    )


def test_tmux_restart_policy_if_not_running_starts_a_stopped_container():
    fake = FakeTmux(containers_running=False)
    backend(fake).start(tmux_plan(instance(), restart_container="if_not_running"))
    assert ("docker", "start", "robot-dev") in fake.commands
    assert not any(command[:2] == ("docker", "restart") for command in fake.commands)


def test_tmux_missing_container_reports_an_actionable_error():
    fake = FakeTmux(missing_containers=("robot-dev",))
    with pytest.raises(ScenarioExecutionError, match="toolchain container create robot-dev"):
        backend(fake).start(tmux_plan(instance()))


def test_tmux_partial_start_failure_cleans_new_session():
    fake = FakeTmux()

    def override(command, _):
        if command[:2] == ("tmux", "new-window"):
            return CommandResult(9, stderr="failed")
        return None

    fake.override = override
    plan = tmux_plan(instance("robot1"), instance("robot2", container="container-b"))
    with pytest.raises(ScenarioExecutionError, match="cannot create tmux window"):
        backend(fake).start(plan)
    assert ("tmux", "kill-session", "-t", "robot-session") in fake.commands
    assert fake.session is False


def test_tmux_uses_direct_arguments_and_refreshes_stale_docker_environment():
    fake = FakeTmux()
    item = instance(groups=(group("drivers", script="/workspace/a script.sh"),))
    backend(
        fake,
        environment={"PATH": "/usr/bin", "DOCKER_HOST": "tcp://host:2375"},
    ).start(tmux_plan(item, keep_alive=False))
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
    backend(fake).start(tmux_plan(item, keep_alive=False))
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


def test_tmux_keep_alive_pane_falls_back_to_a_shell_instead_of_dying():
    fake = FakeTmux()
    backend(fake).start(tmux_plan(instance()))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    assert process[5:7] == ("/bin/sh", "-c")
    program = process[-1]
    assert program.startswith('trap "" INT\ndocker exec -it')
    assert program.endswith("docker exec -it --workdir=/ros2_ws robot-dev /bin/bash -i")
    assert "[toolchain] drivers exited with code $__toolchain_status" in program


def test_tmux_reports_a_group_that_exited_before_keep_alive_shell_started():
    fake = FakeTmux()
    fake.pane_logs["robot-session:robot1.0"] = (
        "docker: Error response from daemon: No such file\n"
        "[toolchain] drivers exited with code 127\n"
        "root@container:/ros2_ws# "
    )
    with pytest.raises(ScenarioExecutionError, match="exit 127.*No such file"):
        backend(fake).start(tmux_plan(instance()))


def test_tmux_keep_alive_can_be_disabled():
    fake = FakeTmux()
    backend(fake).start(tmux_plan(instance(), keep_alive=False))
    process = next(command for command in fake.commands if command[:2] == ("tmux", "respawn-pane"))
    assert process[-1] == "/workspace/drivers.sh"
    assert not any(
        command[:2] == ("tmux", "capture-pane")
        for command in fake.commands
    )


def test_tmux_reports_dead_pane_and_keeps_failure_logs():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.dead["robot-session:robot1.0"] = 127
    fake.pane_logs["robot-session:robot1.0"] = "docker: command not found\n"
    with pytest.raises(ScenarioExecutionError, match="exit 127.*docker: command not found"):
        backend(fake).start(tmux_plan(instance()))
    assert fake.session is True


def test_tmux_stop_interrupts_every_pane_then_kills_the_session():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    tmux_backend = backend(fake)

    plan = tmux_plan(instance(groups=(group("drivers"), group("navigation"))))
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
    plan = tmux_plan(instance("robot2", container="container-b"), partial=True)
    backend(fake).stop(plan)
    assert ("tmux", "kill-window", "-t", "robot-session:robot2") in fake.commands
    assert ("tmux", "kill-window", "-t", "robot-session:robot1") not in fake.commands
    assert fake.windows == ["robot1"]


def test_tmux_logs_requires_an_instance_when_several_are_running():
    fake = FakeTmux(session=True, windows=("robot1", "robot2"))
    plan = tmux_plan(
        instance("robot1"), instance("robot2", container="container-b")
    )
    with pytest.raises(ScenarioPlanError, match="select one with --instance"):
        backend(fake).logs(plan, None, "drivers")


def test_tmux_logs_captures_the_named_group_pane():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    fake.pane_logs["robot-session:robot1.1"] = "navigation log\n"
    plan = tmux_plan(instance(groups=(group("drivers"), group("navigation"))))
    result = backend(fake).logs(plan, "robot1", "navigation")
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
    plan = tmux_plan(instance())
    backend(fake).logs(plan, "robot1", "drivers", follow=True)
    assert ("tmux", "attach-session", "-t", "robot-session") in fake.commands


def test_tmux_attach_selects_the_instance_window_and_group_pane():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    plan = tmux_plan(instance(groups=(group("drivers"), group("navigation"))))
    result = backend(fake).attach(plan, "robot1", "navigation")
    assert result.detail == "detached from robot-session:robot1.1"
    assert ("tmux", "select-window", "-t", "robot-session:robot1") in fake.commands
    assert ("tmux", "select-pane", "-t", "robot-session:robot1.1") in fake.commands


def test_tmux_status_lists_windows_and_panes():
    fake = FakeTmux(session=True, windows=("robot1",))
    fake.panes["robot1"] = ["drivers", "navigation"]
    result = backend(fake).status(tmux_plan(instance()))
    assert "robot1.0 drivers" in result.detail
    assert "robot1.1 navigation" in result.detail


def test_tmux_status_reports_a_missing_session():
    fake = FakeTmux()
    assert backend(fake).status(tmux_plan(instance())).detail == "not running"


def test_compose_tmux_restarts_services_then_resolves_containers_and_uses_panes(tmp_path: Path):
    fake = FakeTmux(compose_services=("robot",))
    plan = tmux_plan(
        instance("robot1", container=None, service="robot"),
        compose_file=tmp_path / "compose.yaml",
        project_name="robot-debug",
    )
    write(tmp_path / "compose.yaml", "services: {robot: {image: ubuntu}}\n")
    backend(fake).start(plan)
    commands = fake.commands
    stop = next(
        index for index, command in enumerate(commands) if command[-2:] == ("stop", "robot")
    )
    up = next(index for index, command in enumerate(commands) if "--wait" in command)
    window = next(
        index for index, command in enumerate(commands) if command[:2] == ("tmux", "new-session")
    )
    assert stop < up < window
    process = next(command for command in commands if command[:2] == ("tmux", "respawn-pane"))
    assert "robot-container" in " ".join(process)


@pytest.mark.parametrize("stage", ["validation", "stop", "up", "replicas"])
def test_compose_tmux_failures_do_not_create_windows(tmp_path: Path, stage: str):
    write(tmp_path / "compose.yaml", "services: {robot: {image: ubuntu}}\n")
    fake = FakeTmux(compose_services=("other",) if stage == "validation" else ("robot",))

    def override(command, _):
        if stage == "stop" and command[-2:] == ("stop", "robot"):
            return CommandResult(1, stderr="stop failed")
        if stage == "up" and "--wait" in command:
            return CommandResult(1, stderr="up failed")
        if stage == "replicas" and command[-3:] == ("ps", "-q", "robot"):
            return CommandResult(0, "one\ntwo\n")
        return None

    fake.override = override
    plan = tmux_plan(
        instance("robot1", container=None, service="robot"),
        compose_file=tmp_path / "compose.yaml",
        project_name="robot-debug",
    )
    with pytest.raises((ScenarioExecutionError, ScenarioPlanError)):
        backend(fake).start(plan)
    assert not any(command[:2] == ("tmux", "new-session") for command in fake.commands)


def compose_plan(tmp_path: Path, *instances: ScenarioInstancePlan) -> ComposeSupervisorPlan:
    compose = write(tmp_path / "compose.yaml", "services: {}\n")
    return ComposeSupervisorPlan(
        "robot",
        "deployment",
        compose,
        "robot-prod",
        tmp_path / "generated",
        instances or (instance(service="robot"),),
    )


def test_compose_start_writes_one_config_per_instance_service(tmp_path: Path):
    fake = FakeTmux()
    plan = compose_plan(
        tmp_path,
        instance("robot1", service="robot", groups=(group("drivers"),)),
        instance("robot2", service="robot2", groups=(group("drivers"), group("navigation"))),
    )
    result = ComposeSupervisorBackend(fake).start(plan)

    assert result.detail == "compose:robot-prod"
    first = (tmp_path / "generated/robot.conf").read_text()
    second = (tmp_path / "generated/robot2.conf").read_text()
    assert "[program:drivers]" in first
    assert "[program:navigation]" not in first
    assert "[program:navigation]" in second
    assert fake.commands[-1] == (
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
    fake = FakeTmux()
    generated = tmp_path / "generated"
    write(generated / "stale.conf", "; Generated by toolchain. Do not edit.\nold\n")
    manual = write(generated / "manual.conf", "[program:manual]\n")

    ComposeSupervisorBackend(fake).start(compose_plan(tmp_path, instance(service="robot")))

    assert not (generated / "stale.conf").exists()
    assert manual.read_text() == "[program:manual]\n"


def test_compose_status_and_group_logs(tmp_path: Path):
    fake = FakeTmux()

    def override(command, _):
        if command[-1] == "ps":
            return CommandResult(0, "running\n")
        if "logs" in command:
            return CommandResult(0, "navigation log\n")
        return None

    fake.override = override
    plan = compose_plan(
        tmp_path,
        instance("robot1", service="robot", groups=(group("navigation"),)),
    )
    backend = ComposeSupervisorBackend(fake)
    assert backend.status(plan).detail == "running"
    assert backend.logs(plan, "robot1", "navigation").detail == "navigation log"
    assert fake.commands[-1][-2:] == ("logs", "robot")
    with pytest.raises(ScenarioPlanError, match="only available for tmux"):
        backend.attach(plan)


def test_compose_logs_rejects_ambiguous_group(tmp_path: Path):
    fake = FakeTmux()
    plan = compose_plan(
        tmp_path,
        instance("robot1", service="robot", groups=(group("drivers"),)),
        instance("robot2", service="robot2", groups=(group("drivers"),)),
    )
    with pytest.raises(ScenarioPlanError, match="several instances"):
        ComposeSupervisorBackend(fake).logs(plan, None, "drivers")


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
                "--no-attach",
                "--non-interactive",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Backend: tmux" in output
    assert "Instances: robot1" in output
    assert "Window robot1: robot-dev -> drivers" in output
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
    development: {backend: tmux, attach: false}
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
    assert "Window robot2: container-b -> drivers" in output


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
    class Broken:
        def run(self, *_args, **_kwargs):
            raise FileNotFoundError("missing")

    with pytest.raises(Exception, match="cannot execute tmux"):
        TmuxScenarioBackend(Broken()).start(tmux_plan(instance()))


def test_compose_runner_failure_is_actionable(tmp_path: Path):
    fake = FakeTmux()

    def override(command, _):
        if command[-2:] == ("up", "-d"):
            return CommandResult(8, stderr="compose failed")
        return None

    fake.override = override
    with pytest.raises(ScenarioExecutionError, match="compose failed"):
        ComposeSupervisorBackend(fake).start(compose_plan(tmp_path, instance(service="robot")))


def test_compose_runner_os_error_is_actionable(tmp_path: Path):
    class Broken:
        def run(self, *_args, **_kwargs):
            raise FileNotFoundError("missing")

    with pytest.raises(Exception, match="cannot execute Docker Compose"):
        ComposeSupervisorBackend(Broken()).start(compose_plan(tmp_path, instance()))
