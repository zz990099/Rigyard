"""Application service orchestrating a complete layered image build."""

from __future__ import annotations

from .backend import ImageBuildBackend
from .models import ImageBuildPlan, ImageBuildResult


class ImageBuildService:
    def __init__(
        self,
        backend: ImageBuildBackend,
    ) -> None:
        self.backend = backend

    def build(self, plan: ImageBuildPlan) -> ImageBuildResult:
        self.backend.check_available()
        results = tuple(self.backend.build_step(step) for step in plan.steps)
        return ImageBuildResult(
            image_name=plan.image_name,
            final_tag=plan.final_tag,
            steps=results,
        )
