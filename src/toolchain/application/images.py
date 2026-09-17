"""Application use case for building a configured image."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from ..config.loader import load_config
from ..errors import ImageConfigError
from ..images.backend import ImageBuildBackend
from ..images.models import ImageBuildPlan, ImageBuildResult, ImageSpec
from ..images.planner import ImageBuildPlanner
from ..images.service import ImageBuildService
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .parameters import resolve_template
from .requests import BuildImageRequest


class BuildImageUseCase:
    def __init__(self, backend: ImageBuildBackend) -> None:
        self.backend = backend

    def plan(
        self,
        request: BuildImageRequest,
        *,
        environment: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ImageBuildPlan:
        config = load_config(request.config_path)
        if request.image_name not in config.images:
            available = ", ".join(sorted(config.images)) or "none"
            raise ImageConfigError(
                f"unknown image {request.image_name!r}; configured images: {available}"
            )
        host_environment = dict(os.environ if environment is None else environment)
        renderer = StringTemplateRenderer(
            TemplateContext.capture(host_environment, now=now, config_path=request.config_path)
        )
        spec, _ = resolve_template(
            config,
            config.images[request.image_name],
            request.resolution_request(),
            f"images.{request.image_name}",
            ImageSpec,
            renderer,
        )
        return ImageBuildPlanner().create_plan(
            request.image_name,
            spec,
            request.config_path,
        )

    def execute(self, plan: ImageBuildPlan) -> ImageBuildResult:
        return ImageBuildService(self.backend).build(plan)
