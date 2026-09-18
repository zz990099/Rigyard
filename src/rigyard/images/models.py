"""Template, resolved configuration, and immutable image execution models."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..parameters.models import PromptValue

BUILD_ARG_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
IMAGE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
Scalar = str | int | float | bool
RuntimeString = PromptValue | str
RuntimeScalar = PromptValue | Scalar


def _validate_build_arg_names(values: Mapping[str, Any]) -> None:
    invalid = sorted(name for name in values if not BUILD_ARG_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid build argument name(s): {', '.join(invalid)}")


class ImageLayerTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    dockerfile: Path | PromptValue
    build_args: dict[str, RuntimeScalar] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not IMAGE_NAME.fullmatch(value):
            raise ValueError(f"invalid layer name {value!r}")
        return value

    @field_validator("build_args")
    @classmethod
    def valid_build_args(cls, value: dict[str, RuntimeScalar]) -> dict[str, RuntimeScalar]:
        _validate_build_arg_names(value)
        return value


class ImageTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
    base: RuntimeString
    context: Path | PromptValue = Path(".")
    tag: RuntimeString
    tag_alias: RuntimeString | None = None
    layers: tuple[ImageLayerTemplate, ...] = Field(min_length=1)
    build_args: dict[str, RuntimeScalar] = Field(default_factory=dict)

    @field_validator("build_args")
    @classmethod
    def valid_build_args(cls, value: dict[str, RuntimeScalar]) -> dict[str, RuntimeScalar]:
        _validate_build_arg_names(value)
        return value

    @model_validator(mode="after")
    def unique_layer_names(self) -> ImageTemplate:
        names = [layer.name for layer in self.layers]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate layer name(s): {', '.join(duplicates)}")
        return self


class ImageLayerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    dockerfile: Path
    build_args: dict[str, Scalar] = Field(default_factory=dict)


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
    base: str
    context: Path = Path(".")
    tag: str
    tag_alias: str | None = None
    layers: tuple[ImageLayerSpec, ...] = Field(min_length=1)
    build_args: dict[str, Scalar] = Field(default_factory=dict)


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
    tag_alias: str | None = None


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
    tag_alias: str | None = None
