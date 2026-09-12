"""Typed container definitions and immutable resolved plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..parameters.references import ParameterRef


class EnvironmentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    default: str | None = None


ValueSource = str | ParameterRef | EnvironmentRef


class MountSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["bind", "volume"] = "bind"
    source: ValueSource
    target: ValueSource
    read_only: bool = Field(default=False, strict=True)


class ContainerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
    image: ValueSource
    name: ValueSource | None = None
    interactive: bool = Field(default=True, strict=True)
    tty: bool = Field(default=True, strict=True)
    detach: Literal[True] = True
    privileged: bool = Field(default=False, strict=True)
    devices: tuple[ValueSource, ...] = ()
    group_add: tuple[ValueSource, ...] = ()
    mounts: tuple[MountSpec, ...] = ()
    network: ValueSource | None = None
    ipc: ValueSource | None = None
    workdir: ValueSource | None = None
    environment: dict[str, ValueSource] = Field(default_factory=dict)
    command: tuple[ValueSource, ...] = ()

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, ValueSource]) -> dict[str, ValueSource]:
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in values):
            raise ValueError("invalid container environment variable name")
        return values


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
