"""Scenario operation service independent of concrete process managers."""

from __future__ import annotations

from .backend import ScenarioBackend
from .models import ScenarioPlan, ScenarioResult


class ScenarioService:
    def __init__(self, backend: ScenarioBackend) -> None:
        self.backend = backend

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.backend.start(plan)

    def stop(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.backend.stop(plan)

    def status(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.backend.status(plan)

    def attach(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult:
        return self.backend.attach(plan, instance_name, group_name)

    def logs(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult:
        return self.backend.logs(plan, instance_name, group_name, follow=follow)
