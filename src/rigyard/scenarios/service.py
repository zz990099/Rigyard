"""Application service for tmux-based development scenarios."""

from __future__ import annotations

from .executor import ScenarioExecutor
from .models import ScenarioPlan, ScenarioResult


class ScenarioService:
    def __init__(self, executor: ScenarioExecutor | None = None) -> None:
        self.executor = executor or ScenarioExecutor()

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.executor.start(plan)

    def stop(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.executor.stop(plan)

    def down(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.executor.down(plan)

    def status(self, plan: ScenarioPlan) -> ScenarioResult:
        return self.executor.status(plan)

    def attach(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult:
        return self.executor.attach(plan, instance_name, group_name)

    def logs(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult:
        return self.executor.logs(plan, instance_name, group_name, follow=follow)
