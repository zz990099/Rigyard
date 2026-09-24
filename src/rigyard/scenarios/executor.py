"""Execute development scenarios with tmux in existing or Compose containers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping

from ..errors import ScenarioExecutionError, ScenarioPlanError
from ..execution import CommandRunner, SubprocessRunner
from .lifecycle import ComposeLifecycleBackend, ContainerLifecycleBackend
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
from .tmux import PANE_GROUP_OPTION as PANE_GROUP_OPTION
from .tmux import TmuxSessionBackend

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
        self.containers = ContainerLifecycleBackend(self.commands, sleep_fn)
        self.compose = ComposeLifecycleBackend(self.commands, self.environment)
        self.tmux = TmuxSessionBackend(self.commands, self.runner, self.environment)

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        self.tmux.require()
        self.containers.require()
        if plan.compose is not None:
            self.compose.preflight(plan)
        if self.tmux.session_exists(plan.session):
            self.stop(plan)
        if plan.compose is not None and not plan.partial:
            self.compose.remove(plan)
        runtime_plan = self.compose.prepare(plan) if plan.compose is not None else plan
        if plan.compose is None:
            self.containers.restart(runtime_plan)
        self.containers.check(runtime_plan)

        created = False
        created_session = False
        try:
            for index, instance in enumerate(runtime_plan.instances):
                # A partial start joins the session another instance already owns.
                created_session = (
                    self.tmux.create_window(runtime_plan.session, instance.name) or created_session
                )
                created = True
                if index == 0:
                    self.tmux.configure_session(runtime_plan.session, mouse=runtime_plan.mouse)
                window = self._window_target(runtime_plan, instance)
                self.tmux.configure_window(window)
                for _ in instance.groups[1:]:
                    self.tmux.split_window(window, instance.name)
                panes = self.tmux.panes(window)
                if len(panes) != len(instance.groups):
                    raise ScenarioExecutionError(
                        f"tmux window {instance.name!r} has {len(panes)} pane(s) "
                        f"but {len(instance.groups)} group(s)"
                    )
                for group_index, (group, (_, pane_index)) in enumerate(
                    zip(instance.groups, panes, strict=True)
                ):
                    target = f"{window}.{pane_index}"
                    self.tmux.start_pane(
                        target,
                        self._pane_command(runtime_plan, instance, group),
                        group.name,
                    )
                    self._wait_for_next(instance.startup, group_index, len(instance.groups))
                self.tmux.tile(window, instance.name)
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
        self.tmux.require()
        self.containers.require()
        self.compose.require()
        self.stop(plan)
        self.compose.remove(plan)
        return ScenarioResult(plan.scene_name, plan.profile_name, "down")

    def stop(self, plan: ScenarioPlan) -> ScenarioResult:
        self.tmux.require()
        if not self.tmux.session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        running = [instance for instance in plan.instances if self._window_exists(plan, instance)]
        self._interrupt(plan, running)
        if running and plan.stop_grace_seconds:
            self.sleep_fn(plan.stop_grace_seconds)
        if not plan.partial:
            self.tmux.kill_session(plan.session)
            return ScenarioResult(plan.scene_name, plan.profile_name, "stopped")
        for instance in running:
            if self._window_exists(plan, instance):
                self.tmux.kill_window(self._window_target(plan, instance), instance.name)
        detail = "stopped" if running else "not running"
        return ScenarioResult(plan.scene_name, plan.profile_name, detail)

    def _interrupt(self, plan: ScenarioPlan, instances: list[ScenarioInstancePlan]) -> None:
        for instance in instances:
            window = self._window_target(plan, instance)
            for _, pane_index in self.tmux.panes(window):
                self.tmux.interrupt(f"{window}.{pane_index}")

    def _clean_up(self, plan: ScenarioPlan, created_session: bool) -> None:
        if created_session:
            self.tmux.kill_session(plan.session, checked=False)
            return
        for instance in plan.instances:
            self.tmux.kill_window(self._window_target(plan, instance), instance.name, checked=False)

    def status(self, plan: ScenarioPlan) -> ScenarioResult:
        self.tmux.require()
        if not self.tmux.session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        if plan.partial:
            details = [
                self.tmux.status(plan.session, instance.name).stdout.strip()
                for instance in plan.instances
                if self._window_exists(plan, instance)
            ]
            return ScenarioResult(
                plan.scene_name, plan.profile_name, "\n".join(details) or "not running"
            )
        result = self.tmux.status(plan.session)
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.strip())

    def attach(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult:
        self.tmux.require()
        if not self.tmux.session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        target = plan.session
        if instance_name is not None or group_name is not None:
            instance, group, index = self._resolve_pane(plan, instance_name, group_name)
            window = self._window_target(plan, instance)
            if not self._window_exists(plan, instance):
                raise ScenarioExecutionError(f"tmux window {instance.name!r} is not running")
            target = window
            self.tmux.select_window(window, instance.name)
            target = f"{window}.{index}"
            self.tmux.select_pane(target, group.name)
        self.tmux.attach(plan.session)
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
        self.tmux.require()
        if not self.tmux.session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        instance, group, index = self._resolve_pane(plan, instance_name, group_name)
        target = f"{self._window_target(plan, instance)}.{index}"
        result = self.tmux.capture(target, f"cannot capture logs for group {group.name!r}")
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.rstrip())

    # -- tmux inspection ---------------------------------------------------

    def _window_exists(self, plan: ScenarioPlan, instance: ScenarioInstancePlan) -> bool:
        return self.tmux.window_exists(plan.session, instance.name)

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
        panes = {title: index for title, index in self.tmux.panes(window)}
        if group_name is None:
            if not instance.groups:
                raise ScenarioPlanError(f"scenario instance {instance.name!r} has no groups")
            group = instance.groups[0]
        else:
            selected_group = next(
                (item for item in instance.groups if item.name == group_name), None
            )
            if selected_group is None:
                raise ScenarioPlanError(
                    f"unknown scenario group {group_name!r} in instance {instance.name!r}"
                )
            group = selected_group
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
        docker.append(self.containers.target(instance))
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

    def _wait_for_next(
        self,
        startup: ScenarioStartupPlan,
        index: int,
        count: int,
    ) -> None:
        if startup.mode == "sequential" and startup.interval_seconds > 0 and index + 1 < count:
            self.sleep_fn(startup.interval_seconds)

    def _check_started_panes(self, plan: ScenarioPlan) -> None:
        self.sleep_fn(STARTUP_GRACE_SECONDS)
        for instance in plan.instances:
            window = self._window_target(plan, instance)
            if not self._window_exists(plan, instance):
                continue
            for title, pane_index in self.tmux.panes(window):
                target = f"{window}.{pane_index}"
                result = self.tmux.startup_state(target, title)
                state = result.stdout.split()
                if state and state[0] == "1":
                    logs = self.tmux.capture(
                        target,
                        f"cannot capture startup failure for group {title!r}",
                    )
                    pane_exit_status = state[1] if len(state) > 1 else "unknown"
                    raise ScenarioExecutionError(
                        f"group {title!r} in instance {instance.name!r} exited during startup "
                        f"(exit {pane_exit_status}); tmux session {plan.session!r} was kept "
                        "for diagnosis: " + logs.stdout.strip()
                    )
                if not plan.keep_alive:
                    continue
                logs = self.tmux.capture(
                    target,
                    f"cannot capture startup output for group {title!r}",
                )
                startup_code = startup_exit_code(logs.stdout, title)
                if startup_code is None:
                    continue
                raise ScenarioExecutionError(
                    f"group {title!r} in instance {instance.name!r} exited during startup "
                    f"(exit {startup_code}); its pane fell back to a container shell, and "
                    f"tmux session {plan.session!r} was kept for diagnosis: " + logs.stdout.strip()
                )
