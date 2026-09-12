"""Application use case for building a configured image."""

from __future__ import annotations

from ..config.loader import load_config
from ..errors import ImageConfigError
from ..images.backend import ImageBuildBackend
from ..images.models import ImageBuildResult
from ..images.service import ImageBuildService
from .parameters import resolve_loaded_parameters
from .requests import BuildImageRequest


class BuildImageUseCase:
    def __init__(self, backend: ImageBuildBackend) -> None:
        self.backend = backend

    def execute(self, request: BuildImageRequest) -> ImageBuildResult:
        config = load_config(request.config_path)
        if request.image_name not in config.images:
            available = ", ".join(sorted(config.images)) or "none"
            raise ImageConfigError(
                f"unknown image {request.image_name!r}; configured images: {available}"
            )
        context = resolve_loaded_parameters(config, request.parameter_request())
        return ImageBuildService(self.backend).build(
            request.image_name,
            config.images[request.image_name],
            context,
            request.config_path,
        )

