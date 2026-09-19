"""Shared application use case for custom tasks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..config.loader import load_config
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
        config = load_config(request.config_path)
        template = find_definition(
            config,
            "tasks",
            task_name,
            request.source_path,
            request.config_path,
        )
        if template is None:
            available = ", ".join(sorted(config.tasks)) or "none"
            raise SchemaValidationError(
                f"unknown task {task_name!r}; configured tasks: {available}"
            )
        host_environment = dict(os.environ if environment is None else environment)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                host_environment,
                now=now,
                config_path=request.config_path,
                variables=config.variables,
            )
        )
        spec, _ = resolve_template(
            config,
            template,
            request,
            f"tasks.{task_name}",
            TaskSpec,
            renderer,
            self.sources,
            self.formatter,
        )
        return TaskPlanner().create_plan(task_name, spec)

    def execute(self, plan: TaskPlan) -> TaskResult:
        return self.service.execute(plan)
