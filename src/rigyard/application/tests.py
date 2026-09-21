"""Shared application use case for user-defined test commands."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..config.loader import load_config
from ..errors import SchemaValidationError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from ..tests.backend import TestBackend
from ..tests.models import TestAction, TestPlan, TestResult, TestSpec
from ..tests.planner import TestPlanner
from ..tests.service import TestService
from .definitions import find_definition
from .parameters import resolve_template
from .requests import ResolutionRequest


class ExecuteTestUseCase:
    def __init__(
        self,
        backend: TestBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.service = TestService(backend)
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
        config = load_config(request.config_path)
        match = find_definition(
            config,
            "tests",
            test_name,
            request.source_path,
            request.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.tests)) or "none"
            raise SchemaValidationError(
                f"unknown test {test_name!r}; configured tests: {available}"
            )
        host_environment = dict(os.environ if environment is None else environment)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(
                host_environment,
                now=now,
                config_path=request.config_path,
                variables=config.variables,
            ).with_source(match.source_path)
        )
        spec, _ = resolve_template(
            config,
            match.value,
            request,
            f"tests.{test_name}",
            TestSpec,
            renderer,
            self.sources,
            self.formatter,
        )
        return TestPlanner().create_plan(test_name, action, spec)

    def execute(self, plan: TestPlan) -> TestResult:
        return self.service.execute(plan)
