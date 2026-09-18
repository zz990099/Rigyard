"""Backend port consumed by the image application service."""

from __future__ import annotations

from typing import Protocol

from .models import BuildStepResult, ImageBuildStep


class ImageBuildBackend(Protocol):
    def check_available(self) -> None:
        """Raise when the backend cannot execute builds."""

    def build_step(self, step: ImageBuildStep) -> BuildStepResult:
        """Build exactly one fully materialized image step."""

    def tag_image(self, source: str, alias: str) -> None:
        """Add a tag to the completed image, raising on failure."""
