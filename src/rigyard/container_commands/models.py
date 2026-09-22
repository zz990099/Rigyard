"""Common template, spec, and plan fields for container-backed commands."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..execution import TtyMode
from ..parameters.models import PromptValue

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RuntimeText = PromptValue | str
RuntimePath = PromptValue | Path
RuntimeList = PromptValue | tuple[str, ...]
RuntimeInteger = PromptValue | int


class ContainerCommandTemplate(BaseModel):
    """Runtime-resolvable fields shared by builds, tests, and tasks."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "command"

    description: str | None = None
    container: RuntimeText
    workdir: RuntimePath | None = None
    user: RuntimeText | None = None
    setup: RuntimeList = ()
    environment: dict[str, RuntimeText] = Field(default_factory=dict)
    tty: TtyMode = "auto"
    start_container: bool = True

    @field_validator("container")
    @classmethod
    def container_is_not_empty(cls, value: RuntimeText) -> RuntimeText:
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{cls.command_kind} container must not be empty")
        return value

    @field_validator("setup")
    @classmethod
    def setup_entries_are_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and any(not item for item in value):
            raise ValueError(f"{cls.command_kind} setup entries must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, RuntimeText]) -> dict[str, RuntimeText]:
        _validate_environment(values, cls.command_kind)
        return values


class ContainerCommandSpec(BaseModel):
    """Resolved fields shared by container-backed command specs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    command_kind: ClassVar[str] = "command"

    description: str | None = None
    container: str = Field(min_length=1)
    workdir: Path | None = None
    user: str | None = None
    setup: tuple[str, ...] = ()
    environment: dict[str, str] = Field(default_factory=dict)
    tty: TtyMode = "auto"
    start_container: bool = True

    @field_validator("setup")
    @classmethod
    def setup_entries_are_not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError(f"{cls.command_kind} setup entries must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, str]) -> dict[str, str]:
        _validate_environment(values, cls.command_kind)
        return values


@dataclass(frozen=True)
class ContainerCommandPlan:
    """Normalized execution fields embedded in domain-specific plans."""

    container: str
    command: tuple[str, ...]
    workdir: Path | None
    user: str | None
    setup: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    environment_overrides: tuple[str, ...]
    timeout_seconds: int | None
    tty: TtyMode
    start_container: bool = field(default=True, kw_only=True)


def _validate_environment(values: Mapping[str, object], kind: str) -> None:
    invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid {kind} environment variable name(s): {', '.join(invalid)}")
