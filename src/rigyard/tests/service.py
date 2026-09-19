"""Application service for user-defined test commands."""

from __future__ import annotations

from .backend import TestBackend
from .models import TestPlan, TestResult


class TestService:
    def __init__(self, backend: TestBackend) -> None:
        self.backend = backend

    def execute(self, plan: TestPlan) -> TestResult:
        return self.backend.execute(plan)
