"""Manifest, source-file, and assembled project configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from ..builds.models import BuildTemplate
from ..containers.models import ContainerTemplate
from ..images.models import IMAGE_NAME, ImageTemplate


def _invalid_names(values: dict[str, object]) -> list[str]:
    return sorted(name for name in values if not IMAGE_NAME.fullmatch(name))


class ToolchainMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_is_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("metadata.name must not be empty")
        return value


class ToolchainSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: Path | None = None
    containers: Path | None = None
    builds: Path | None = None

    @model_validator(mode="after")
    def at_least_one_source(self) -> ToolchainSources:
        if self.images is None and self.containers is None and self.builds is None:
            raise ValueError("at least one configuration source is required")
        return self


class ToolchainManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2]
    metadata: ToolchainMetadata
    sources: ToolchainSources


class ImageDefinitions(RootModel[dict[str, ImageTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, ImageTemplate]) -> dict[str, ImageTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid image name(s): {', '.join(invalid)}")
        return value


class ContainerDefinitions(RootModel[dict[str, ContainerTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, ContainerTemplate]) -> dict[str, ContainerTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid container name(s): {', '.join(invalid)}")
        return value


class BuildDefinitions(RootModel[dict[str, BuildTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, BuildTemplate]) -> dict[str, BuildTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid build name(s): {', '.join(invalid)}")
        return value


class ToolchainConfig(BaseModel):
    """Fully loaded immutable configuration used by application services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2]
    metadata: ToolchainMetadata
    sources: ToolchainSources
    images: dict[str, ImageTemplate] = Field(default_factory=dict)
    containers: dict[str, ContainerTemplate] = Field(default_factory=dict)
    builds: dict[str, BuildTemplate] = Field(default_factory=dict)

    @field_validator("images")
    @classmethod
    def valid_image_names(cls, value: dict[str, ImageTemplate]) -> dict[str, ImageTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid image name(s): {', '.join(invalid)}")
        return value

    @field_validator("containers")
    @classmethod
    def valid_container_names(
        cls, value: dict[str, ContainerTemplate]
    ) -> dict[str, ContainerTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid container name(s): {', '.join(invalid)}")
        return value

    @field_validator("builds")
    @classmethod
    def valid_build_names(cls, value: dict[str, BuildTemplate]) -> dict[str, BuildTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid build name(s): {', '.join(invalid)}")
        return value
