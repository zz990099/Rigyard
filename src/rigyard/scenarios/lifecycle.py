"""Docker container and Compose lifecycle backends for scenarios."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import replace

from ..errors import ScenarioExecutionError, ScenarioPlanError
from .models import ScenarioInstancePlan, ScenarioPlan
from .runtime import ScenarioCommandGateway


class ContainerLifecycleBackend:
    def __init__(
        self,
        commands: ScenarioCommandGateway,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.commands = commands
        self.sleep_fn = sleep_fn

    def require(self) -> None:
        self.commands.require(("docker", "version"), "Docker")

    def restart(self, plan: ScenarioPlan) -> None:
        for instance in plan.instances:
            container = self.target(instance)
            running = self.commands.container_running(container)
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
            self.commands.checked(
                command,
                f"cannot {action} container {container!r}; recreate it with "
                f"'rigyard container create {container}'",
            )
            self._wait_until_running(container)

    def check(self, plan: ScenarioPlan) -> None:
        containers = (self.target(instance) for instance in plan.instances)
        for container in dict.fromkeys(containers):
            if not self.commands.container_running(container):
                raise ScenarioExecutionError(f"container {container!r} is not running")

    @staticmethod
    def target(instance: ScenarioInstancePlan) -> str:
        if instance.container is None:
            raise ScenarioExecutionError(
                f"scenario instance {instance.name!r} has no container target"
            )
        return instance.container

    def _wait_until_running(
        self,
        container: str,
        *,
        attempts: int = 20,
        interval: float = 0.25,
    ) -> None:
        for attempt in range(attempts):
            if self.commands.container_running(container):
                return
            if attempt + 1 < attempts:
                self.sleep_fn(interval)
        raise ScenarioExecutionError(f"container {container!r} did not reach running state")


class ComposeLifecycleBackend:
    def __init__(
        self,
        commands: ScenarioCommandGateway,
        environment: Mapping[str, str],
    ) -> None:
        self.commands = commands
        self.environment = environment

    def require(self) -> None:
        self.commands.require(("docker", "compose", "version"), "Docker Compose")

    def preflight(self, plan: ScenarioPlan) -> None:
        self.require()
        result = self.commands.checked(
            (*self._base(plan), "config", "--services"),
            "cannot validate Compose services",
            environment=self._environment(plan),
        )
        available = set(result.stdout.splitlines())
        missing = set(self._services(plan)) - available
        if missing:
            raise ScenarioPlanError("unknown Compose service(s): " + ", ".join(sorted(missing)))

    def prepare(self, plan: ScenarioPlan) -> ScenarioPlan:
        if plan.compose is None:
            return plan
        base = self._base(plan)
        services = self._services(plan)
        self.commands.checked(
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
            environment=self._environment(plan),
        )
        containers: dict[str, str] = {}
        for service in services:
            result = self.commands.checked(
                (*base, "ps", "-q", service),
                f"cannot locate Compose service {service!r}",
                environment=self._environment(plan),
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
                replace(instance, container=containers[self._service(instance)])
                for instance in plan.instances
            ),
        )

    def remove(self, plan: ScenarioPlan) -> None:
        self.commands.checked(
            (*self._base(plan), "down", "--remove-orphans"),
            "Docker Compose down failed",
            environment=self._environment(plan),
        )

    @staticmethod
    def _service(instance: ScenarioInstancePlan) -> str:
        if instance.service is None:
            raise ScenarioPlanError(f"scenario instance {instance.name!r} has no Compose service")
        return instance.service

    def _services(self, plan: ScenarioPlan) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._service(instance) for instance in plan.instances))

    @staticmethod
    def _base(plan: ScenarioPlan) -> tuple[str, ...]:
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

    def _environment(self, plan: ScenarioPlan) -> dict[str, str]:
        if plan.compose is None:
            raise ScenarioPlanError("scenario is not managed by Docker Compose")
        return {**self.environment, **dict(plan.compose.environment)}
