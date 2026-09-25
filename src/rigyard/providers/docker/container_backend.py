"""Docker run and lifecycle hook adapter. No host shell is invoked."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from ...containers.models import (
    ContainerCreateResult,
    ContainerHookPlan,
    ContainerHookResult,
    ContainerRunPlan,
)
from ...errors import BackendUnavailableError, ContainerCreateError, ContainerLifecycleError
from ...execution import (
    CommandRunner,
    SubprocessRunner,
    cancel_docker_exec,
    cancellable_docker_exec,
)


class DockerContainerBackend:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        confirm_replace: Callable[[str], bool] | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.confirm_replace = confirm_replace or (lambda _: False)

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
            mount_value = f"type={mount.type},source={mount.source},target={mount.target}"
            if mount.read_only:
                mount_value += ",readonly"
            args.append(f"--mount={mount_value}")
        for flag, option_value in (
            ("network", plan.network),
            ("ipc", plan.ipc),
            ("workdir", plan.workdir),
        ):
            if option_value is not None:
                args.append(f"--{flag}={option_value}")
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
            existing = self.runner.run(
                ("docker", "ps", "-a", "--format", "{{.ID}} {{.Names}}"), capture=True
            )
            if existing.returncode:
                raise BackendUnavailableError("cannot list Docker containers")
            container_id = next(
                (
                    parts[0]
                    for line in existing.stdout.splitlines()
                    if len(parts := line.split()) == 2 and parts[1] == plan.container_name
                ),
                None,
            )
            if container_id is not None:
                if not self.confirm_replace(
                    f"Container {plan.container_name!r} already exists. "
                    "Delete it and create a new one?"
                ):
                    raise ContainerCreateError(
                        f"container {plan.container_name!r} already exists; creation cancelled"
                    )
                removed = self.runner.run(("docker", "rm", "-f", container_id), capture=True)
                if removed.returncode:
                    raise ContainerCreateError(
                        f"cannot remove existing container {plan.container_name!r}"
                    )
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
        invocation = cancellable_docker_exec(
            self.hook_command(container_id, hook),
            container_id,
        )
        try:
            result = self.runner.run(
                invocation.command,
                stdin=hook.script_content,
                capture=True,
                timeout_seconds=hook.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            cancellation_error = cancel_docker_exec(self.runner, invocation.cancel_command)
            suffix = f"; {cancellation_error}" if cancellation_error else ""
            raise ContainerLifecycleError(
                self._hook_error(
                    container_name,
                    container_id,
                    hook,
                    f"timed out after {hook.timeout_seconds} seconds{suffix}",
                )
            ) from exc
        except KeyboardInterrupt as exc:
            cancellation_error = cancel_docker_exec(self.runner, invocation.cancel_command)
            if cancellation_error:
                raise ContainerLifecycleError(
                    self._hook_error(
                        container_name,
                        container_id,
                        hook,
                        f"was interrupted; {cancellation_error}",
                    )
                ) from exc
            raise
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
