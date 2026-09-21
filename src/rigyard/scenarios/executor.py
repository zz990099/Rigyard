"""Execute development scenarios with tmux in existing or Compose containers."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import replace

from ..errors import ScenarioExecutionError, ScenarioPlanError
from ..execution import CommandResult, CommandRunner, SubprocessRunner
from .models import (
    ScenarioGroupPlan,
    ScenarioInstancePlan,
    ScenarioPlan,
    ScenarioResult,
    ScenarioStartupPlan,
)
from .process import (
    container_session_argv,
    host_shell_argv,
    keep_alive_argv,
    process_argv,
    startup_exit_code,
)
from .runtime import ScenarioCommandGateway

PLACEHOLDER = "import time; time.sleep(86400)"
PANE_GROUP_OPTION = "@rigyard_group"
PANE_BORDER_FORMAT = f"#{{pane_index}}: #{{{PANE_GROUP_OPTION}}}"
# Give the pane program a moment to report an immediate failure before we look.
STARTUP_GRACE_SECONDS = 0.4


class ScenarioExecutor:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.commands = ScenarioCommandGateway(self.runner)
        self.sleep_fn = sleep_fn
        self.environment = os.environ if environment is None else environment

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        self._require_docker()
        if plan.compose is not None:
            self._preflight_compose(plan)
        if self._session_exists(plan.session):
            self.stop(plan)
        if plan.compose is not None and not plan.partial:
            self._remove_compose(plan)
        runtime_plan = self._prepare_compose(plan) if plan.compose is not None else plan
        if plan.compose is None:
            self._restart_containers(runtime_plan)
        self._check_containers(runtime_plan)

        created = False
        created_session = False
        try:
            for index, instance in enumerate(runtime_plan.instances):
                # A partial start joins the session another instance already owns.
                if self._session_exists(runtime_plan.session):
                    create = (
                        "tmux",
                        "new-window",
                        "-d",
                        "-t",
                        runtime_plan.session,
                        "-n",
                        instance.name,
                    )
                else:
                    create = (
                        "tmux",
                        "new-session",
                        "-d",
                        "-s",
                        runtime_plan.session,
                        "-n",
                        instance.name,
                    )
                    created_session = True
                # Start a known live process instead of tmux's configurable default shell.
                self._checked(
                    (*create, sys.executable, "-c", PLACEHOLDER),
                    f"cannot create tmux window {instance.name!r}",
                )
                created = True
                if index == 0:
                    self._sync_environment(runtime_plan)
                    self._configure_session(runtime_plan)
                window = self._window_target(runtime_plan, instance)
                self._configure_window(window)
                for _ in instance.groups[1:]:
                    self._checked(
                        (
                            "tmux",
                            "split-window",
                            "-d",
                            "-t",
                            window,
                            sys.executable,
                            "-c",
                            PLACEHOLDER,
                        ),
                        f"cannot split tmux window {instance.name!r}",
                    )
                    # split-window always splits the window's current pane, so without
                    # re-tiling the same pane is halved again and again until tmux
                    # answers "no space for new pane" (a window with 11 groups dies on a
                    # default 80x24 session). Tiling keeps every pane big enough for the
                    # next split, which is what the earlier startup scripts did.
                    self._checked(
                        ("tmux", "select-layout", "-t", window, "tiled"),
                        f"cannot lay out tmux window {instance.name!r}",
                    )
                panes = self._panes(window)
                if len(panes) != len(instance.groups):
                    raise ScenarioExecutionError(
                        f"tmux window {instance.name!r} has {len(panes)} pane(s) "
                        f"but {len(instance.groups)} group(s)"
                    )
                for group_index, (group, (_, pane_index)) in enumerate(
                    zip(instance.groups, panes, strict=True)
                ):
                    target = f"{window}.{pane_index}"
                    self._checked(
                        (
                            "tmux",
                            "respawn-pane",
                            "-k",
                            "-t",
                            target,
                            *self._pane_command(runtime_plan, instance, group),
                        ),
                        f"cannot start tmux pane {group.name!r}",
                    )
                    self._checked(
                        (
                            "tmux",
                            "set-option",
                            "-p",
                            "-t",
                            target,
                            PANE_GROUP_OPTION,
                            group.name,
                        ),
                        f"cannot tag tmux pane {group.name!r}",
                    )
                    self._checked(
                        ("tmux", "select-pane", "-t", target, "-T", group.name),
                        f"cannot title tmux pane {group.name!r}",
                    )
                    self._wait_for_next(instance.startup, group_index, len(instance.groups))
                self._checked(
                    ("tmux", "select-layout", "-t", window, "tiled"),
                    f"cannot lay out tmux window {instance.name!r}",
                )
                self._wait_for_next(runtime_plan.startup, index, len(runtime_plan.instances))
        except Exception:
            if created:
                self._clean_up(runtime_plan, created_session)
            raise

        self._check_started_panes(runtime_plan)
        result = ScenarioResult(plan.scene_name, plan.profile_name, f"tmux:{plan.session}")
        if plan.attach:
            self.attach(runtime_plan)
        return result

    def down(self, plan: ScenarioPlan) -> ScenarioResult:
        if plan.compose is None:
            raise ScenarioPlanError("scene down is only available for Compose-managed scenarios")
        if plan.partial:
            raise ScenarioPlanError("scene down does not support partial instance selection")
        self._require_tmux()
        self._require_docker()
        self._require_compose()
        self.stop(plan)
        self._remove_compose(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name, "down")

    def stop(self, plan: ScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        running = [instance for instance in plan.instances if self._window_exists(plan, instance)]
        self._interrupt(plan, running)
        if running and plan.stop_grace_seconds:
            self.sleep_fn(plan.stop_grace_seconds)
        if not plan.partial:
            self._checked(
                ("tmux", "kill-session", "-t", plan.session),
                f"cannot stop tmux session {plan.session!r}",
            )
            return ScenarioResult(plan.scene_name, plan.profile_name, "stopped")
        for instance in running:
            if self._window_exists(plan, instance):
                self._checked(
                    ("tmux", "kill-window", "-t", self._window_target(plan, instance)),
                    f"cannot stop tmux window {instance.name!r}",
                )
        detail = "stopped" if running else "not running"
        return ScenarioResult(plan.scene_name, plan.profile_name, detail)

    def _interrupt(self, plan: ScenarioPlan, instances: list[ScenarioInstancePlan]) -> None:
        for instance in instances:
            window = self._window_target(plan, instance)
            for _, pane_index in self._panes(window):
                self.runner.run(
                    ("tmux", "send-keys", "-t", f"{window}.{pane_index}", "C-c"),
                    capture=True,
                )

    def _clean_up(self, plan: ScenarioPlan, created_session: bool) -> None:
        if created_session:
            self.runner.run(("tmux", "kill-session", "-t", plan.session), capture=True)
            return
        for instance in plan.instances:
            self.runner.run(
                ("tmux", "kill-window", "-t", self._window_target(plan, instance)),
                capture=True,
            )

    def status(self, plan: ScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        result = self._checked(
            (
                "tmux",
                "list-panes",
                "-s",
                "-t",
                plan.session,
                "-F",
                "#{window_name}.#{pane_index} #{pane_title} "
                "dead=#{pane_dead} exit=#{pane_exit_status}",
            ),
            f"cannot inspect tmux session {plan.session!r}",
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.strip())

    def attach(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        target = plan.session
        if instance_name is not None or group_name is not None:
            instance, group, index = self._resolve_pane(plan, instance_name, group_name)
            window = self._window_target(plan, instance)
            if not self._window_exists(plan, instance):
                raise ScenarioExecutionError(f"tmux window {instance.name!r} is not running")
            target = window
            self._checked(
                ("tmux", "select-window", "-t", window),
                f"cannot select tmux window {instance.name!r}",
            )
            target = f"{window}.{index}"
            self._checked(
                ("tmux", "select-pane", "-t", target),
                f"cannot select tmux pane {group.name!r}",
            )
        attach_command = "switch-client" if self.environment.get("TMUX") else "attach-session"
        self._checked(
            ("tmux", attach_command, "-t", plan.session),
            f"cannot attach tmux session {plan.session!r}",
            capture=False,
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, f"detached from {target}")

    def logs(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult:
        if follow:
            return self.attach(plan, instance_name, group_name)
        self._require_tmux()
        if not self._session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        instance, group, index = self._resolve_pane(plan, instance_name, group_name)
        target = f"{self._window_target(plan, instance)}.{index}"
        result = self._checked(
            ("tmux", "capture-pane", "-p", "-t", target, "-S", "-"),
            f"cannot capture logs for group {group.name!r}",
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.rstrip())

    # -- preflight ---------------------------------------------------------

    def _require_tmux(self) -> None:
        self._require(("tmux", "-V"), "tmux")

    def _require_docker(self) -> None:
        self._require(("docker", "version"), "Docker")

    def _require_compose(self) -> None:
        self._require(("docker", "compose", "version"), "Docker Compose")

    def _require(self, command: tuple[str, ...], label: str) -> None:
        self.commands.require(command, label)

    def _compose_base(self, plan: ScenarioPlan) -> tuple[str, ...]:
        if plan.compose is None:
            raise ScenarioPlanError("scenario is not managed by Docker Compose")
        return (
            "docker",
            "compose",
            "-f",
            str(plan.compose.file),
            "--project-name",
            plan.compose.project_name,
        )

    def _instance_service(self, instance: ScenarioInstancePlan) -> str:
        if instance.service is None:
            raise ScenarioPlanError(f"scenario instance {instance.name!r} has no Compose service")
        return instance.service

    def _compose_services(self, plan: ScenarioPlan) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._instance_service(instance) for instance in plan.instances))

    def _compose_environment(self, plan: ScenarioPlan) -> dict[str, str]:
        if plan.compose is None:
            raise ScenarioPlanError("scenario is not managed by Docker Compose")
        return {**self.environment, **dict(plan.compose.environment)}

    def _preflight_compose(self, plan: ScenarioPlan) -> None:
        self._require_compose()
        result = self._checked(
            (*self._compose_base(plan), "config", "--services"),
            "cannot validate Compose services",
            environment=self._compose_environment(plan),
        )
        available = set(result.stdout.splitlines())
        missing = set(self._compose_services(plan)) - available
        if missing:
            raise ScenarioPlanError("unknown Compose service(s): " + ", ".join(sorted(missing)))

    def _prepare_compose(self, plan: ScenarioPlan) -> ScenarioPlan:
        if plan.compose is None:
            return plan
        base = self._compose_base(plan)
        services = self._compose_services(plan)
        self._checked(
            (
                *base,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                str(plan.compose.wait_timeout_seconds),
                *services,
            ),
            "Docker Compose up failed",
            environment=self._compose_environment(plan),
        )
        containers: dict[str, str] = {}
        for service in services:
            result = self._checked(
                (*base, "ps", "-q", service),
                f"cannot locate Compose service {service!r}",
                environment=self._compose_environment(plan),
            )
            ids = result.stdout.split()
            if len(ids) != 1:
                raise ScenarioExecutionError(
                    f"Compose service {service!r} must produce exactly one container"
                )
            containers[service] = ids[0]
        return replace(
            plan,
            instances=tuple(
                replace(
                    instance,
                    container=containers[self._instance_service(instance)],
                )
                for instance in plan.instances
            ),
        )

    def _remove_compose(self, plan: ScenarioPlan) -> None:
        self._checked(
            (*self._compose_base(plan), "down", "--remove-orphans"),
            "Docker Compose down failed",
            environment=self._compose_environment(plan),
        )

    def _instance_container(self, instance: ScenarioInstancePlan) -> str:
        if instance.container is None:
            raise ScenarioExecutionError(
                f"scenario instance {instance.name!r} has no container target"
            )
        return instance.container

    def _restart_containers(self, plan: ScenarioPlan) -> None:
        for instance in plan.instances:
            container = self._instance_container(instance)
            running = self._container_running(container)
            if plan.restart_container == "never":
                continue
            if plan.restart_container == "if_not_running" and running:
                continue
            if plan.restart_container == "always":
                command = ("docker", "restart", container)
                action = "restart"
            else:
                command = ("docker", "start", container)
                action = "start"
            self._checked(
                command,
                f"cannot {action} container {container!r}; recreate it with "
                f"'rigyard container create {container}'",
            )
            self._wait_container_running(container)

    def _check_containers(self, plan: ScenarioPlan) -> None:
        containers = (self._instance_container(instance) for instance in plan.instances)
        for container in dict.fromkeys(containers):
            if not self._container_running(container):
                raise ScenarioExecutionError(f"container {container!r} is not running")

    def _container_running(self, container: str) -> bool:
        return self.commands.container_running(container)

    def _wait_container_running(
        self,
        container: str,
        *,
        attempts: int = 20,
        interval: float = 0.25,
    ) -> None:
        for attempt in range(attempts):
            if self._container_running(container):
                return
            if attempt + 1 < attempts:
                self.sleep_fn(interval)
        raise ScenarioExecutionError(f"container {container!r} did not reach running state")

    # -- tmux inspection ---------------------------------------------------

    def _session_exists(self, session: str) -> bool:
        return self.commands.session_exists(session)

    def _window_exists(self, plan: ScenarioPlan, instance: ScenarioInstancePlan) -> bool:
        return self.commands.window_exists(plan.session, instance.name)

    def _panes(self, window: str) -> tuple[tuple[str, int], ...]:
        return self.commands.panes(window, PANE_GROUP_OPTION)

    def _window_target(self, plan: ScenarioPlan, instance: ScenarioInstancePlan) -> str:
        return f"{plan.session}:{instance.name}"

    def _instance(self, plan: ScenarioPlan, name: str | None) -> ScenarioInstancePlan:
        if name is None:
            if len(plan.instances) != 1:
                available = ", ".join(instance.name for instance in plan.instances)
                raise ScenarioPlanError(
                    f"scenario {plan.scene_name!r} runs several instances "
                    f"({available}); select one with --instance"
                )
            return plan.instances[0]
        for instance in plan.instances:
            if instance.name == name:
                return instance
        raise ScenarioPlanError(f"unknown scenario instance {name!r}")

    def _resolve_pane(
        self,
        plan: ScenarioPlan,
        instance_name: str | None,
        group_name: str | None,
    ) -> tuple[ScenarioInstancePlan, ScenarioGroupPlan, int]:
        instance = self._instance(plan, instance_name)
        window = self._window_target(plan, instance)
        panes = {title: index for title, index in self._panes(window)}
        if group_name is None:
            if not instance.groups:
                raise ScenarioPlanError(f"scenario instance {instance.name!r} has no groups")
            group = instance.groups[0]
        else:
            group = next((item for item in instance.groups if item.name == group_name), None)
            if group is None:
                raise ScenarioPlanError(
                    f"unknown scenario group {group_name!r} in instance {instance.name!r}"
                )
        if group.name not in panes:
            raise ScenarioExecutionError(f"tmux pane for group {group.name!r} is not running")
        return instance, group, panes[group.name]

    def _docker_exec(
        self,
        plan: ScenarioPlan,
        instance: ScenarioInstancePlan,
        group: ScenarioGroupPlan,
        *,
        argv: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        docker = ["docker", "exec", "-it"]
        if group.user is not None:
            docker.append(f"--user={group.user}")
        if group.workdir is not None:
            docker.append(f"--workdir={group.workdir}")
        docker.extend(f"--env={key}={value}" for key, value in group.environment)
        docker.append(self._instance_container(instance))
        docker.extend(process_argv(group) if argv is None else argv)
        return tuple(docker)

    def _pane_command(
        self,
        plan: ScenarioPlan,
        instance: ScenarioInstancePlan,
        group: ScenarioGroupPlan,
    ) -> tuple[str, ...]:
        if not plan.keep_alive:
            return self._docker_exec(plan, instance, group)
        primary = self._docker_exec(plan, instance, group, argv=container_session_argv(group))
        return keep_alive_argv(primary, group.name, host_shell_argv(self.environment))

    def _configure_session(self, plan: ScenarioPlan) -> None:
        self._checked(
            ("tmux", "set-option", "-t", plan.session, "mouse", "on" if plan.mouse else "off"),
            "cannot configure tmux mouse mode",
        )

    def _wait_for_next(
        self,
        startup: ScenarioStartupPlan,
        index: int,
        count: int,
    ) -> None:
        if startup.mode == "sequential" and startup.interval_seconds > 0 and index + 1 < count:
            self.sleep_fn(startup.interval_seconds)

    def _configure_window(self, window: str) -> None:
        for command, message in (
            (("set-option", "-w", "-t", window, "remain-on-exit", "on"), "remain-on-exit"),
            (("set-option", "-w", "-t", window, "pane-border-status", "top"), "pane border"),
            (
                ("set-option", "-w", "-t", window, "pane-border-format", PANE_BORDER_FORMAT),
                "pane border format",
            ),
        ):
            self._checked(("tmux", *command), f"cannot configure tmux {message}")

    def _sync_environment(self, plan: ScenarioPlan) -> None:
        # A persistent tmux server may have stale PATH or Docker connection settings.
        for key in (
            "PATH",
            "HOME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        ):
            command = ("tmux", "set-environment", "-t", plan.session)
            if key in self.environment:
                command = (*command, key, self.environment[key])
            else:
                command = (*command, "-r", key)
            self._checked(command, f"cannot configure tmux environment {key!r}")

    def _check_started_panes(self, plan: ScenarioPlan) -> None:
        self.sleep_fn(STARTUP_GRACE_SECONDS)
        for instance in plan.instances:
            window = self._window_target(plan, instance)
            if not self._window_exists(plan, instance):
                continue
            for title, pane_index in self._panes(window):
                target = f"{window}.{pane_index}"
                result = self._checked(
                    (
                        "tmux",
                        "display-message",
                        "-p",
                        "-t",
                        target,
                        "#{pane_dead} #{pane_exit_status}",
                    ),
                    f"cannot inspect startup of group {title!r}",
                )
                state = result.stdout.split()
                if state and state[0] == "1":
                    logs = self._checked(
                        ("tmux", "capture-pane", "-p", "-t", target, "-S", "-"),
                        f"cannot capture startup failure for group {title!r}",
                    )
                    code = state[1] if len(state) > 1 else "unknown"
                    raise ScenarioExecutionError(
                        f"group {title!r} in instance {instance.name!r} exited during startup "
                        f"(exit {code}); tmux session {plan.session!r} was kept for diagnosis: "
                        + logs.stdout.strip()
                    )
                if not plan.keep_alive:
                    continue
                logs = self._checked(
                    ("tmux", "capture-pane", "-p", "-t", target, "-S", "-"),
                    f"cannot capture startup output for group {title!r}",
                )
                code = startup_exit_code(logs.stdout, title)
                if code is None:
                    continue
                raise ScenarioExecutionError(
                    f"group {title!r} in instance {instance.name!r} exited during startup "
                    f"(exit {code}); its pane fell back to a container shell, and "
                    f"tmux session {plan.session!r} was kept for diagnosis: " + logs.stdout.strip()
                )

    def _checked(
        self,
        command: tuple[str, ...],
        message: str,
        *,
        capture: bool = True,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        return self.commands.checked(
            command,
            message,
            capture=capture,
            environment=environment,
        )
