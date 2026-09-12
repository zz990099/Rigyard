"""Composition model for the complete toolchain YAML document."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..containers.models import ContainerSpec
from ..images.models import IMAGE_NAME, ImageSpec
from ..parameters.models import ParameterSchema, ParameterSpec


class ToolchainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(strict=True)
    parameters: dict[str, ParameterSpec] = Field(default_factory=dict)
    images: dict[str, ImageSpec] = Field(default_factory=dict)
    containers: dict[str, ContainerSpec] = Field(default_factory=dict)

    @field_validator("containers")
    @classmethod
    def valid_container_keys(cls, value: dict[str, ContainerSpec]) -> dict[str, ContainerSpec]:
        if any(not IMAGE_NAME.fullmatch(name) for name in value):
            raise ValueError("invalid container configuration name")
        return value

    @field_validator("version")
    @classmethod
    def only_version_one(cls, value: int) -> int:
        if value != 1:
            raise ValueError("only schema version 1 is supported")
        return value

    @field_validator("images")
    @classmethod
    def valid_image_names(cls, value: dict[str, ImageSpec]) -> dict[str, ImageSpec]:
        invalid = sorted(name for name in value if not IMAGE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid image name(s): {', '.join(invalid)}")
        return value

    @model_validator(mode="after")
    def validate_parameters(self) -> ToolchainConfig:
        self.parameter_schema()
        return self

    def parameter_schema(self) -> ParameterSchema:
        return ParameterSchema(version=self.version, parameters=self.parameters)
