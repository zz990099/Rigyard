"""Template, resolved configuration, and immutable project build models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from ..container_commands.models import (
    ContainerCommandPlan,
    ContainerCommandSpec,
    ContainerCommandTemplate,
    RuntimeInteger,
    RuntimeList,
    RuntimePath,
)


class BuildTemplate(ContainerCommandTemplate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "build"

    script: RuntimePath
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    timeout_seconds: RuntimeInteger | None = None

    @field_validator("interpreter")
    @classmethod
    def fixed_interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("build interpreter must not be empty")
        return value


class BuildSpec(ContainerCommandSpec):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "build"

    script: Path
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    timeout_seconds: int | None = Field(default=None, gt=0, le=86400)


@dataclass(frozen=True)
class BuildPlan(ContainerCommandPlan):
    build_name: str
    script: Path


@dataclass(frozen=True)
class BuildResult:
    build_name: str
    command: tuple[str, ...]
