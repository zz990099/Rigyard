"""Application service orchestrating a complete layered image build."""

from __future__ import annotations

from pathlib import Path

from ..parameters.context import ResolvedContext
from .backend import ImageBuildBackend
from .models import ImageBuildResult, ImageSpec
from .planner import ImageBuildPlanner


class ImageBuildService:
    def __init__(
        self,
        backend: ImageBuildBackend,
        planner: ImageBuildPlanner | None = None,
    ) -> None:
        self.backend = backend
        self.planner = planner or ImageBuildPlanner()

    def build(
        self,
        image_name: str,
        spec: ImageSpec,
        context: ResolvedContext,
        config_path: str | Path,
    ) -> ImageBuildResult:
        plan = self.planner.create_plan(image_name, spec, context, config_path)
        self.backend.check_available()
        results = tuple(self.backend.build_step(step) for step in plan.steps)
        return ImageBuildResult(
            image_name=plan.image_name,
            final_tag=plan.final_tag,
            steps=results,
        )

