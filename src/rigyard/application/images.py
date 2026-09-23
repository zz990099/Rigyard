"""Application use case for building a configured image."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..errors import ImageConfigError
from ..images.backend import ImageBuildBackend
from ..images.models import ImageBuildPlan, ImageBuildResult, ImageSpec
from ..images.planner import ImageBuildPlanner
from ..images.service import ImageBuildService
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .definitions import find_definition
from .parameters import resolve_template
from .project import project_context
from .requests import BuildImageRequest


class BuildImageUseCase:
    def __init__(
        self,
        backend: ImageBuildBackend,
        *,
        sources: DynamicSources | None = None,
        formatter: Formatter | None = None,
    ) -> None:
        self.backend = backend
        self.sources = dict(sources or {})
        self.formatter = formatter

    def plan(
        self,
        request: BuildImageRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ImageBuildPlan:
        project = project_context(
            request.config_path,
            request.project,
            environment=environment,
            timestamp=now,
        )
        config = project.config
        match = find_definition(
            config,
            "images",
            request.image_name,
            request.source_path,
            project.config_path,
        )
        if match is None:
            available = ", ".join(sorted(config.images)) or "none"
            raise ImageConfigError(
                f"unknown image {request.image_name!r}; configured images: {available}"
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
            request.resolution_request(),
            f"images.{request.image_name}",
            ImageSpec,
            renderer,
            self.sources,
            self.formatter,
            environment=project.environment,
        )
        return ImageBuildPlanner().create_plan(
            request.image_name,
            spec,
            project.config_path,
        )

    def execute(self, plan: ImageBuildPlan) -> ImageBuildResult:
        return ImageBuildService(self.backend).build(plan)
