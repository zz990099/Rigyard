"""Execution port for backend-specific scenario operations."""

from __future__ import annotations

from typing import Protocol

from .models import ScenarioPlan, ScenarioResult


class ScenarioBackend(Protocol):
    def start(self, plan: ScenarioPlan) -> ScenarioResult: ...

    def stop(self, plan: ScenarioPlan) -> ScenarioResult: ...

    def status(self, plan: ScenarioPlan) -> ScenarioResult: ...

    def attach(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult: ...

    def logs(
        self,
        plan: ScenarioPlan,
        instance_name: str | None = None,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult: ...
