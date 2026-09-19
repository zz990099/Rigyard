"""Backend port consumed by the task execution service."""

from __future__ import annotations

from typing import Protocol

from .models import TaskPlan, TaskResult


class TaskBackend(Protocol):
    def execute(self, plan: TaskPlan) -> TaskResult:
        """Execute one fully materialized custom task plan."""
