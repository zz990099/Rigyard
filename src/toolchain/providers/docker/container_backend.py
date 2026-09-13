"""Docker run and lifecycle hook adapter. No host shell is invoked."""

from __future__ import annotations

import subprocess

from ...containers.models import (
    ContainerCreateResult,
    ContainerHookPlan,
    ContainerHookResult,
    ContainerRunPlan,
)
from ...errors import BackendUnavailableError, ContainerCreateError, ContainerLifecycleError
from .runner import CommandRunner, SubprocessRunner


class DockerContainerBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def command(self, plan: ContainerRunPlan) -> tuple[str, ...]:
        args = ["docker", "run"]
        for enabled, flag in (
            (plan.interactive, "-i"),
            (plan.tty, "-t"),
            (True, "-d"),
            (plan.privileged, "--privileged"),
        ):
            if enabled:
                args.append(flag)
        # Use --option=value so values starting with '-' cannot become flags.
        args.append(f"--name={plan.container_name}")
        args.extend(f"--device={value}" for value in plan.devices)
        args.extend(f"--group-add={value}" for value in plan.group_add)
        for mount in plan.mounts:
            value = f"type={mount.type},source={mount.source},target={mount.target}"
            if mount.read_only:
                value += ",readonly"
            args.append(f"--mount={value}")
        for flag, value in (
            ("network", plan.network),
            ("ipc", plan.ipc),
            ("workdir", plan.workdir),
        ):
            if value is not None:
                args.append(f"--{flag}={value}")
        args.extend(f"--env={key}={value}" for key, value in plan.environment)
        args.append(plan.image)
        args.extend(plan.command)
        return tuple(args)

    def hook_command(
        self,
        container_id: str,
        hook: ContainerHookPlan,
    ) -> tuple[str, ...]:
        args = ["docker", "exec", "-i"]
        if hook.user is not None:
            args.append(f"--user={hook.user}")
        if hook.workdir is not None:
            args.append(f"--workdir={hook.workdir}")
        args.extend(f"--env={key}={value}" for key, value in hook.environment)
        args.append(container_id)
        args.extend(hook.interpreter)
        return tuple(args)

    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        try:
            result = self.runner.run(self.command(plan), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute Docker: {exc}") from exc
        if result.returncode:
            detail = self._redacted_detail(
                result.stderr, tuple(value for _, value in plan.environment)
            )
            if not detail:
                detail = f"exit code {result.returncode}"
            raise ContainerCreateError(f"container {plan.container_name!r}: {detail}")
        container_id = result.stdout.strip()
        if not container_id:
            raise ContainerCreateError("Docker returned success without a container ID")
        return ContainerCreateResult(plan.container_name, container_id)

    def run_hook(
        self,
        container_name: str,
        container_id: str,
        hook: ContainerHookPlan,
    ) -> ContainerHookResult:
        try:
            result = self.runner.run(
                self.hook_command(container_id, hook),
                stdin=hook.script_content,
                capture=True,
                timeout_seconds=hook.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ContainerLifecycleError(
                self._hook_error(
                    container_name,
                    container_id,
                    hook,
                    f"timed out after {hook.timeout_seconds} seconds",
                )
            ) from exc
        except OSError as exc:
            raise ContainerLifecycleError(
                self._hook_error(
                    container_name,
                    container_id,
                    hook,
                    f"cannot execute Docker: {type(exc).__name__}",
                )
            ) from exc
        if result.returncode:
            detail = self._redacted_detail(
                result.stderr or result.stdout,
                hook.redact_values,
            )
            if not detail:
                detail = f"exit code {result.returncode}"
            else:
                detail = f"exit {result.returncode}: {detail}"
            raise ContainerLifecycleError(
                self._hook_error(container_name, container_id, hook, detail)
            )
        return ContainerHookResult(hook.phase, hook.name)

    def _hook_error(
        self,
        container_name: str,
        container_id: str,
        hook: ContainerHookPlan,
        detail: str,
    ) -> str:
        return (
            f"container {container_name!r} ({container_id}) was created but "
            f"{hook.phase.value} hook {hook.name!r} failed: {detail}; "
            "the container was kept for diagnosis"
        )

    def _redacted_detail(
        self,
        detail: str,
        values: tuple[str, ...],
    ) -> str:
        redacted = detail.strip()
        for value in values:
            if value:
                redacted = redacted.replace(value, "<redacted>")
        return redacted
