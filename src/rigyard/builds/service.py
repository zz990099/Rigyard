"""Application service for project builds."""

from __future__ import annotations

from .backend import BuildBackend
from .models import BuildPlan, BuildResult


class BuildService:
    def __init__(self, backend: BuildBackend) -> None:
        self.backend = backend

    def execute(self, plan: BuildPlan) -> BuildResult:
        return self.backend.execute(plan)
