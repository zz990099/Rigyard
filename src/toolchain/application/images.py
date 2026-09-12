"""Application use case for building a configured image."""

from __future__ import annotations

from ..config.loader import load_config
from ..errors import ImageConfigError
from ..images.backend import ImageBuildBackend
from ..images.models import ImageBuildPlan, ImageBuildResult, ImageSpec
from ..images.planner import ImageBuildPlanner
from ..images.service import ImageBuildService
from .parameters import resolve_template
from .requests import BuildImageRequest


class BuildImageUseCase:
    def __init__(self, backend: ImageBuildBackend) -> None:
        self.backend = backend

    def plan(self, request: BuildImageRequest) -> ImageBuildPlan:
        config = load_config(request.config_path)
        if request.image_name not in config.images:
            available = ", ".join(sorted(config.images)) or "none"
            raise ImageConfigError(
                f"unknown image {request.image_name!r}; configured images: {available}"
            )
        spec, _ = resolve_template(
            config,
            config.images[request.image_name],
            request.resolution_request(),
            f"images.{request.image_name}",
            ImageSpec,
        )
        return ImageBuildPlanner().create_plan(
            request.image_name,
            spec,
            request.config_path,
        )

    def execute(self, plan: ImageBuildPlan) -> ImageBuildResult:
        return ImageBuildService(self.backend).build(plan)
