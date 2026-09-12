"""Docker run adapter. All arguments are passed without a shell."""

from __future__ import annotations

from ...containers.models import ContainerCreateResult, ContainerRunPlan
from ...errors import BackendUnavailableError, ContainerCreateError
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

    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        try:
            result = self.runner.run(self.command(plan), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute Docker: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            # Docker diagnostics may repeat environment values; redact them.
            for _, value in plan.environment:
                if value:
                    detail = detail.replace(value, "<redacted>")
            raise ContainerCreateError(f"container {plan.container_name!r}: {detail}")
        container_id = result.stdout.strip()
        if not container_id:
            raise ContainerCreateError("Docker returned success without a container ID")
        return ContainerCreateResult(plan.container_name, container_id)
