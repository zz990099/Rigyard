"""Template, resolved configuration, and immutable container plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from ..parameters.models import PromptValue


class EnvironmentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    default: str | None = None


RuntimeText = PromptValue | str
RuntimeBool = PromptValue | StrictBool
RuntimeList = PromptValue | tuple[str, ...]
RuntimeEnvironment = PromptValue | EnvironmentRef | str


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
    command: RuntimeList = ()

    @field_validator("environment")
    @classmethod
    def valid_environment(
        cls, values: dict[str, RuntimeEnvironment]
    ) -> dict[str, RuntimeEnvironment]:
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in values):
            raise ValueError("invalid container environment variable name")
        return values


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
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContainerMount:
    type: str
    source: str
    target: str
    read_only: bool


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


@dataclass(frozen=True)
class ContainerCreateResult:
    container_name: str
    container_id: str
