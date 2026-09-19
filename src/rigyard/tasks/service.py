"""Application service for custom tasks."""

from __future__ import annotations

from .backend import TaskBackend
from .models import TaskPlan, TaskResult


class TaskService:
    def __init__(self, backend: TaskBackend) -> None:
        self.backend = backend

    def execute(self, plan: TaskPlan) -> TaskResult:
        return self.backend.execute(plan)
