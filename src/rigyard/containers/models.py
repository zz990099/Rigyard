"""Template, resolved configuration, and immutable container plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from ..parameters.models import PromptValue

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HOOK_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class EnvironmentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    env: str = Field(pattern=ENVIRONMENT_NAME.pattern)
    default: str | None = None


RuntimeText = PromptValue | str
RuntimeBool = PromptValue | StrictBool
RuntimeList = PromptValue | tuple[str, ...]
RuntimeInteger = PromptValue | int
RuntimePath = PromptValue | Path
RuntimeEnvironment = PromptValue | EnvironmentRef | str


def _validate_environment(values: dict[str, object], field: str) -> None:
    if any(not ENVIRONMENT_NAME.fullmatch(key) for key in values):
        raise ValueError(f"invalid {field} environment variable name")


class ContainerHookTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    script: RuntimePath
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    user: RuntimeText | None = None
    workdir: RuntimeText | None = None
    environment: dict[str, RuntimeEnvironment] = Field(default_factory=dict)
    timeout_seconds: RuntimeInteger = 300

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not HOOK_NAME.fullmatch(value):
            raise ValueError(f"invalid lifecycle hook name {value!r}")
        return value

    @field_validator("interpreter")
    @classmethod
    def fixed_interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("hook interpreter must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(
        cls, values: dict[str, RuntimeEnvironment]
    ) -> dict[str, RuntimeEnvironment]:
        _validate_environment(values, "hook")
        return values


class ContainerLifecycleTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    post_create: tuple[ContainerHookTemplate, ...] = ()
    post_start: tuple[ContainerHookTemplate, ...] = ()

    @model_validator(mode="after")
    def unique_names_per_phase(self) -> ContainerLifecycleTemplate:
        for phase in ("post_create", "post_start"):
            names = [hook.name for hook in getattr(self, phase)]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise ValueError(
                    f"duplicate {phase} lifecycle hook name(s): {', '.join(duplicates)}"
                )
        return self


class ContainerTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
    image: RuntimeText
    name: RuntimeText | None = None
    interactive: RuntimeBool = True
    tty: RuntimeBool = True
    detach: Literal[True] = True
    privileged: RuntimeBool = False
    devices: RuntimeList = ()
    group_add: RuntimeList = ()
    mounts: RuntimeList = ()
    network: RuntimeText | None = None
    ipc: RuntimeText | None = None
    workdir: RuntimeText | None = None
    environment: dict[str, RuntimeEnvironment] = Field(default_factory=dict)
    lifecycle: ContainerLifecycleTemplate = Field(default_factory=ContainerLifecycleTemplate)
    command: RuntimeList = ()

    @field_validator("environment")
    @classmethod
    def valid_environment(
        cls, values: dict[str, RuntimeEnvironment]
    ) -> dict[str, RuntimeEnvironment]:
        _validate_environment(values, "container")
        return values


class ContainerHookSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    script: Path
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    user: str | None = None
    workdir: str | None = None
    environment: dict[str, str | EnvironmentRef] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, gt=0, le=86400)


class ContainerLifecycleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    post_create: tuple[ContainerHookSpec, ...] = ()
    post_start: tuple[ContainerHookSpec, ...] = ()


class ContainerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
    image: str
    name: str | None = None
    interactive: bool = True
    tty: bool = True
    detach: Literal[True] = True
    privileged: bool = False
    devices: tuple[str, ...] = ()
    group_add: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    network: str | None = None
    ipc: str | None = None
    workdir: str | None = None
    environment: dict[str, str | EnvironmentRef] = Field(default_factory=dict)
    lifecycle: ContainerLifecycleSpec = Field(default_factory=ContainerLifecycleSpec)
    command: tuple[str, ...] = ()


class LifecyclePhase(str, Enum):
    POST_CREATE = "post_create"
    POST_START = "post_start"


@dataclass(frozen=True)
class ContainerMount:
    type: str
    source: str
    target: str
    read_only: bool


@dataclass(frozen=True)
class ContainerHookPlan:
    phase: LifecyclePhase
    name: str
    script_path: Path
    script_content: str
    script_sha256: str
    interpreter: tuple[str, ...]
    user: str | None
    workdir: str | None
    environment: tuple[tuple[str, str], ...]
    redact_values: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class ContainerRunPlan:
    container_name: str
    image: str
    interactive: bool
    tty: bool
    privileged: bool
    devices: tuple[str, ...]
    group_add: tuple[str, ...]
    mounts: tuple[ContainerMount, ...]
    network: str | None
    ipc: str | None
    workdir: str | None
    environment: tuple[tuple[str, str], ...]
    command: tuple[str, ...]
    hooks: tuple[ContainerHookPlan, ...] = ()


@dataclass(frozen=True)
class ContainerHookResult:
    phase: LifecyclePhase
    name: str


@dataclass(frozen=True)
class ContainerCreateResult:
    container_name: str
    container_id: str
    hooks: tuple[ContainerHookResult, ...] = ()
