"""Configuration and immutable execution models for layered images."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..parameters.models import PARAMETER_NAME

BUILD_ARG_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
IMAGE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")

Scalar = str | int | float | bool


class ParameterRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parameter: str

    @field_validator("parameter")
    @classmethod
    def valid_parameter_name(cls, value: str) -> str:
        if not PARAMETER_NAME.fullmatch(value):
            raise ValueError(f"invalid parameter name {value!r}")
        return value


ScalarSource = Scalar | ParameterRef
StringSource = str | ParameterRef


class ImageLayerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    dockerfile: Path
    build_args: dict[str, ScalarSource] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not IMAGE_NAME.fullmatch(value):
            raise ValueError(f"invalid layer name {value!r}")
        return value

    @field_validator("build_args")
    @classmethod
    def valid_build_arg_names(
        cls, value: dict[str, ScalarSource]
    ) -> dict[str, ScalarSource]:
        _validate_build_arg_names(value)
        return value


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    base: StringSource
    context: Path = Path(".")
    tag: StringSource
    layers: tuple[ImageLayerSpec, ...] = Field(min_length=1)
    build_args: dict[str, ScalarSource] = Field(default_factory=dict)

    @field_validator("build_args")
    @classmethod
    def valid_build_arg_names(
        cls, value: dict[str, ScalarSource]
    ) -> dict[str, ScalarSource]:
        _validate_build_arg_names(value)
        return value

    @model_validator(mode="after")
    def unique_layer_names(self) -> ImageSpec:
        names = [layer.name for layer in self.layers]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate layer name(s): {', '.join(duplicates)}")
        return self


def _validate_build_arg_names(values: Mapping[str, Any]) -> None:
    invalid = sorted(name for name in values if not BUILD_ARG_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid build argument name(s): {', '.join(invalid)}")


@dataclass(frozen=True)
class ImageBuildStep:
    index: int
    layer_name: str
    base_image: str
    output_tag: str
    context: Path
    dockerfile_fragment: str
    build_args: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "build_args", MappingProxyType(dict(self.build_args)))


@dataclass(frozen=True)
class ImageBuildPlan:
    image_name: str
    final_tag: str
    steps: tuple[ImageBuildStep, ...]


@dataclass(frozen=True)
class BuildStepResult:
    index: int
    layer_name: str
    output_tag: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class ImageBuildResult:
    image_name: str
    final_tag: str
    steps: tuple[BuildStepResult, ...]
