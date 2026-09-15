"""Composition helper selecting a scenario provider from a validated plan."""

from __future__ import annotations

from ..scenarios.backend import ScenarioBackend
from ..scenarios.models import ComposeSupervisorPlan, ScenarioPlan
from .supervisor import ComposeSupervisorBackend
from .tmux import TmuxScenarioBackend


def scenario_backend(plan: ScenarioPlan) -> ScenarioBackend:
    if isinstance(plan, ComposeSupervisorPlan):
        return ComposeSupervisorBackend()
    return TmuxScenarioBackend()
