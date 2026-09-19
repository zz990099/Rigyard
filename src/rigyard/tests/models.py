"""Template, resolved configuration, and immutable test execution models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..parameters.models import PromptValue

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RuntimeText = PromptValue | str
RuntimePath = PromptValue | Path
RuntimeList = PromptValue | tuple[str, ...]
RuntimeInteger = PromptValue | int
TestAction = Literal["run", "report"]


def _validate_environment(values: dict[str, object]) -> None:
    invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid test environment variable name(s): {', '.join(invalid)}")


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


class TestTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    container: RuntimeText
    workdir: RuntimePath | None = None
    user: RuntimeText | None = None
    setup: RuntimeList = ()
    environment: dict[str, RuntimeText] = Field(default_factory=dict)
    run: TestActionTemplate
    report: TestActionTemplate

    @field_validator("container")
    @classmethod
    def container_is_not_empty(cls, value: RuntimeText) -> RuntimeText:
        if isinstance(value, str) and not value.strip():
            raise ValueError("test container must not be empty")
        return value

    @field_validator("setup")
    @classmethod
    def setup_entries_are_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and any(not item for item in value):
            raise ValueError("test setup entries must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, RuntimeText]) -> dict[str, RuntimeText]:
        _validate_environment(values)
        return values


class TestActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    script: Path
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    timeout_seconds: int | None = Field(default=None, gt=0, le=86400)


class TestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    container: str = Field(min_length=1)
    workdir: Path | None = None
    user: str | None = None
    setup: tuple[str, ...] = ()
    environment: dict[str, str] = Field(default_factory=dict)
    run: TestActionSpec
    report: TestActionSpec

    @field_validator("setup")
    @classmethod
    def setup_entries_are_not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("test setup entries must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, str]) -> dict[str, str]:
        _validate_environment(values)
        return values


@dataclass(frozen=True)
class TestPlan:
    test_name: str
    action: TestAction
    container: str
    script: Path
    command: tuple[str, ...]
    workdir: Path | None
    user: str | None
    setup: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    environment_overrides: tuple[str, ...]
    timeout_seconds: int | None


@dataclass(frozen=True)
class TestResult:
    test_name: str
    action: TestAction
    command: tuple[str, ...]
