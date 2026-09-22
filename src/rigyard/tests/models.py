"""Template, resolved configuration, and immutable test execution models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..container_commands.models import (
    ContainerCommandPlan,
    ContainerCommandSpec,
    ContainerCommandTemplate,
    RuntimeInteger,
    RuntimeList,
    RuntimePath,
)

TestAction = Literal["run", "report"]


class TestActionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    script: RuntimePath
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    timeout_seconds: RuntimeInteger | None = None

    @field_validator("interpreter")
    @classmethod
    def fixed_interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("test interpreter must not be empty")
        return value


class TestTemplate(ContainerCommandTemplate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "test"

    run: TestActionTemplate
    report: TestActionTemplate


class TestActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    script: Path
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    timeout_seconds: int | None = Field(default=None, gt=0, le=86400)


class TestSpec(ContainerCommandSpec):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "test"

    run: TestActionSpec
    report: TestActionSpec


@dataclass(frozen=True)
class TestPlan(ContainerCommandPlan):
    test_name: str
    action: TestAction
    script: Path


@dataclass(frozen=True)
class TestResult:
    test_name: str
    action: TestAction
    command: tuple[str, ...]
