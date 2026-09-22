"""Backend port consumed by the test execution service."""

from __future__ import annotations

from typing import Protocol

from .models import TestPlan, TestResult


class TestBackend(Protocol):
    def execute(self, plan: TestPlan) -> TestResult:
        """Execute one fully materialized test action plan."""
        raise NotImplementedError
