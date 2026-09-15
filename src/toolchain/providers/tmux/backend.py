"""Host tmux frontend for interactive scenario groups running through docker exec."""

from __future__ import annotations

import os
import shlex
import time
from collections.abc import Callable, Mapping

from ...errors import BackendUnavailableError, ScenarioExecutionError, ScenarioPlanError
from ...execution import CommandResult, CommandRunner, SubprocessRunner
from ...scenarios.models import ScenarioGroupPlan, ScenarioResult, TmuxScenarioPlan


class TmuxScenarioBackend:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.sleep_fn = sleep_fn
        self.environment = os.environ if environment is None else environment

    def start(self, plan: TmuxScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        self._require_docker()
        if self._session_exists(plan.session):
            if not plan.replace:
                raise ScenarioExecutionError(
                    f"tmux session {plan.session!r} already exists; stop it or enable replace"
                )
            self.stop(plan)
        self._check_containers(plan)

        created = False
        try:
            for index, group in enumerate(plan.groups):
                target = f"{plan.session}:{group.name}"
                create = (
                    ("tmux", "new-session", "-d", "-s", plan.session, "-n", group.name)
                    if index == 0
                    else ("tmux", "new-window", "-d", "-t", plan.session, "-n", group.name)
                )
                self._checked(
                    create,
                    f"cannot create tmux {'session' if index == 0 else 'window'} "
                    f"{plan.session if index == 0 else group.name!r}",
                )
                created = True
                self._checked(
                    ("tmux", "set-option", "-w", "-t", target, "remain-on-exit", "on"),
                    f"cannot configure tmux window {group.name!r}",
                )
                self._checked(
                    self._window_command(plan, group),
                    f"cannot start tmux window {group.name!r}",
                )
        except Exception:
            if created:
                self.runner.run(("tmux", "kill-session", "-t", plan.session), capture=True)
            raise

        result = ScenarioResult(plan.scene_name, plan.profile_name, f"tmux:{plan.session}")
        if plan.attach:
            self.attach(plan)
        return result

    def stop(self, plan: TmuxScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        for group in plan.groups:
            self.runner.run(
                ("tmux", "send-keys", "-t", f"{plan.session}:{group.name}", "C-c"),
                capture=True,
            )
        if plan.stop_grace_seconds:
            self.sleep_fn(plan.stop_grace_seconds)
        if not self._session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "stopped")
        self._checked(
            ("tmux", "kill-session", "-t", plan.session),
            f"cannot stop tmux session {plan.session!r}",
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, "stopped")

    def status(self, plan: TmuxScenarioPlan) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            return ScenarioResult(plan.scene_name, plan.profile_name, "not running")
        result = self._checked(
            (
                "tmux",
                "list-windows",
                "-t",
                plan.session,
                "-F",
                "#{window_name} pane_dead=#{pane_dead} exit=#{pane_exit_status}",
            ),
            f"cannot inspect tmux session {plan.session!r}",
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.strip())

    def attach(
        self,
        plan: TmuxScenarioPlan,
        group_name: str | None = None,
    ) -> ScenarioResult:
        self._require_tmux()
        if not self._session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        target = plan.session
        if group_name is not None:
            self._group(plan, group_name)
            target = f"{plan.session}:{group_name}"
            self._checked(
                ("tmux", "select-window", "-t", target),
                f"cannot select tmux group {group_name!r}",
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
        plan: TmuxScenarioPlan,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult:
        if follow:
            return self.attach(plan, group_name)
        self._require_tmux()
        group = self._group(plan, group_name or plan.groups[0].name)
        if not self._session_exists(plan.session):
            raise ScenarioExecutionError(f"tmux session {plan.session!r} is not running")
        result = self._checked(
            ("tmux", "capture-pane", "-p", "-t", f"{plan.session}:{group.name}", "-S", "-"),
            f"cannot capture logs for group {group.name!r}",
        )
        return ScenarioResult(plan.scene_name, plan.profile_name, result.stdout.rstrip())

    def _require_tmux(self) -> None:
        self._require(("tmux", "-V"), "tmux")

    def _require_docker(self) -> None:
        self._require(("docker", "version"), "Docker")

    def _require(self, command: tuple[str, ...], label: str) -> None:
        try:
            result = self.runner.run(command, capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute {label}: {exc}") from exc
        if result.returncode:
            raise BackendUnavailableError(f"{label} is unavailable")

    def _check_containers(self, plan: TmuxScenarioPlan) -> None:
        for container in dict.fromkeys(group.container for group in plan.groups):
            result = self._checked(
                ("docker", "inspect", "--format={{.State.Running}}", container or ""),
                f"cannot inspect container {container!r}",
            )
            if result.stdout.strip() != "true":
                raise ScenarioExecutionError(f"container {container!r} is not running")

    def _session_exists(self, session: str) -> bool:
        try:
            result = self.runner.run(("tmux", "has-session", "-t", session), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute tmux: {exc}") from exc
        return result.returncode == 0

    def _window_command(
        self,
        plan: TmuxScenarioPlan,
        group: ScenarioGroupPlan,
    ) -> tuple[str, ...]:
        docker = ["docker", "exec", "-it"]
        if group.user is not None:
            docker.append(f"--user={group.user}")
        if group.workdir is not None:
            docker.append(f"--workdir={group.workdir}")
        docker.extend(f"--env={key}={value}" for key, value in group.environment)
        docker.append(group.container or "")
        docker.extend(group.interpreter)
        docker.append(group.script)
        tmux = ["tmux", "respawn-pane", "-k", "-t", f"{plan.session}:{group.name}"]
        tmux.append(shlex.join(docker))
        return tuple(tmux)

    def _checked(
        self,
        command: tuple[str, ...],
        message: str,
        *,
        capture: bool = True,
    ) -> CommandResult:
        try:
            result = self.runner.run(command, capture=capture)
        except OSError as exc:
            raise BackendUnavailableError(f"{message}: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else f" (exit {result.returncode})"
            raise ScenarioExecutionError(message + suffix)
        return result

    def _group(self, plan: TmuxScenarioPlan, name: str) -> ScenarioGroupPlan:
        for group in plan.groups:
            if group.name == name:
                return group
        raise ScenarioPlanError(f"unknown scenario group {name!r}")
