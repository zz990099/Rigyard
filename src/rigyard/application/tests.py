"""Shared application use case for user-defined test commands."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..tests.backend import TestBackend
from ..tests.models import TestAction, TestPlan, TestResult, TestSpec
from ..tests.planner import TestPlanner
from .project import project_context
from .requests import ResolutionRequest
from .resolution import resolve_definition


class ExecuteTestUseCase:
    def __init__(
        self,
        backend: TestBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.backend = backend
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        test_name: str,
        action: TestAction,
        request: ResolutionRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> TestPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
        )
        spec = resolve_definition(
            project,
            request,
            "tests",
            test_name,
            TestSpec,
            sources=self.sources,
            formatter=self.formatter,
        )
        return TestPlanner().create_plan(test_name, action, spec)

    def execute(self, plan: TestPlan) -> TestResult:
        return self.backend.execute(plan)
