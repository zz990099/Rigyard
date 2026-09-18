"""Backend port consumed by the project build service."""

from __future__ import annotations

from typing import Protocol

from .models import BuildPlan, BuildResult


class BuildBackend(Protocol):
    def execute(self, plan: BuildPlan) -> BuildResult:
        """Execute one fully materialized project build plan."""
