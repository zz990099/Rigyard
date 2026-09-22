"""Template, resolved configuration, and immutable task execution models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..container_commands.models import (
    ContainerCommandPlan,
    ContainerCommandSpec,
    ContainerCommandTemplate,
    RuntimeInteger,
    RuntimeList,
    RuntimePath,
)


class TaskMenu(BaseModel):
    """Optional presentation settings for the fixed Tasks menu."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    label: str | None = None
    confirm: bool = True

    @field_validator("label")
    @classmethod
    def label_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("task menu label must not be blank")
        return value


class TaskTemplate(ContainerCommandTemplate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "task"

    script: RuntimePath
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    timeout_seconds: RuntimeInteger | None = None
    menu: TaskMenu | None = None

    @field_validator("interpreter")
    @classmethod
    def fixed_interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("task interpreter must not be empty")
        return value


class TaskSpec(ContainerCommandSpec):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "task"

    script: Path
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    timeout_seconds: int | None = Field(default=None, gt=0, le=86400)
    menu: TaskMenu | None = None


@dataclass(frozen=True)
class TaskPlan(ContainerCommandPlan):
    task_name: str
    script: Path


@dataclass(frozen=True)
class TaskResult:
    task_name: str
    command: tuple[str, ...]
