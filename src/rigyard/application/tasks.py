"""Shared application use case for custom tasks."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..tasks.backend import TaskBackend
from ..tasks.models import TaskPlan, TaskResult, TaskSpec
from ..tasks.planner import TaskPlanner
from ..tasks.service import TaskService
from .project import project_context
from .requests import ResolutionRequest
from .resolution import resolve_definition


class ExecuteTaskUseCase:
    def __init__(
        self,
        backend: TaskBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.service = TaskService(backend)
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        task_name: str,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> TaskPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
        )
        spec = resolve_definition(
            project,
            request,
            "tasks",
            task_name,
            TaskSpec,
            sources=self.sources,
            formatter=self.formatter,
        )
        return TaskPlanner().create_plan(task_name, spec)

    def execute(self, plan: TaskPlan) -> TaskResult:
        return self.service.execute(plan)
