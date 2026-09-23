"""Shared application use case for custom tasks."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..errors import SchemaValidationError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from ..tasks.backend import TaskBackend
from ..tasks.models import TaskPlan, TaskResult, TaskSpec
from ..tasks.planner import TaskPlanner
from ..tasks.service import TaskService
from .definitions import find_definition
from .parameters import resolve_template
from .project import project_context
from .requests import ResolutionRequest


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
        config = project.config
        match = find_definition(
            config,
            "tasks",
            task_name,
            request.source_path,
            project.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.tasks)) or "none"
            raise SchemaValidationError(
                f"unknown task {task_name!r}; configured tasks: {available}"
            )
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                project.environment,
                now=project.timestamp,
                config_path=project.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        spec, _ = resolve_template(
            config,
            match.value,
            request,
            f"tasks.{task_name}",
            TaskSpec,
            renderer,
            self.sources,
            self.formatter,
            environment=project.environment,
        )
        return TaskPlanner().create_plan(task_name, spec)

    def execute(self, plan: TaskPlan) -> TaskResult:
        return self.service.execute(plan)
