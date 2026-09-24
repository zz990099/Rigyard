"""Application use case for building a configured image."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..images.backend import ImageBuildBackend
from ..images.models import ImageBuildPlan, ImageBuildResult, ImageSpec
from ..images.planner import ImageBuildPlanner
from ..images.service import ImageBuildService
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from .project import project_context
from .requests import BuildImageRequest
from .resolution import resolve_definition


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
            workspace_root=request.workspace_root,
        )
        spec = resolve_definition(
            project,
            request.resolution_request(),
            "images",
            request.image_name,
            ImageSpec,
            sources=self.sources,
            formatter=self.formatter,
        )
        return ImageBuildPlanner().create_plan(
            request.image_name,
            spec,
            project.config_path,
        )

    def execute(self, plan: ImageBuildPlan) -> ImageBuildResult:
        return ImageBuildService(self.backend).build(plan)
