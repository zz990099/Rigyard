"""Templates, resolved specs, and immutable plans for named scenarios."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from ..parameters.models import PromptValue

SCENARIO_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

RuntimeText = PromptValue | str
RuntimeBool = PromptValue | StrictBool
RuntimeList = PromptValue | tuple[str, ...]
RuntimeInteger = PromptValue | int
RuntimePath = PromptValue | Path
RuntimeRestart = PromptValue | Literal["false", "unexpected", "true"]


def _validate_named_mapping(values: dict[str, object], label: str) -> None:
    invalid = sorted(name for name in values if not SCENARIO_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid {label} name(s): {', '.join(invalid)}")


class SupervisorOptionsTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    priority: RuntimeInteger = 100
    autorestart: RuntimeRestart = "unexpected"
    startsecs: RuntimeInteger = 3
    startretries: RuntimeInteger = 3
    stopsignal: RuntimeText = "INT"
    stopasgroup: RuntimeBool = True
    killasgroup: RuntimeBool = True
    stopwaitsecs: RuntimeInteger = 15


class ScenarioGroupTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: RuntimeBool = True
    container: RuntimeText | None = None
    service: RuntimeText | None = None
    script: RuntimeText
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    user: RuntimeText | None = None
    workdir: RuntimeText | None = None
    environment: dict[str, RuntimeText] = Field(default_factory=dict)
    supervisor: SupervisorOptionsTemplate = Field(default_factory=SupervisorOptionsTemplate)

    @field_validator("interpreter")
    @classmethod
    def interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("scenario group interpreter must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, RuntimeText]) -> dict[str, RuntimeText]:
        invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid scenario environment variable name(s): {', '.join(invalid)}")
        return values


class TmuxProfileTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["tmux"]
    compose_file: RuntimePath | None = None
    project_name: RuntimeText | None = None
    wait_timeout_seconds: RuntimeInteger = 60
    session: RuntimeText | None = None
    attach: RuntimeBool = True
    replace: RuntimeBool = False
    stop_grace_seconds: RuntimeInteger = 5


class ComposeSupervisorProfileTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["compose-supervisor"]
    compose_file: RuntimePath
    project_name: RuntimeText | None = None
    supervisor_config_dir: RuntimePath


ScenarioProfileTemplate = Annotated[
    TmuxProfileTemplate | ComposeSupervisorProfileTemplate,
    Field(discriminator="backend"),
]


class ScenarioTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    groups: dict[str, ScenarioGroupTemplate] = Field(min_length=1)
    profiles: dict[str, ScenarioProfileTemplate] = Field(min_length=1)

    @field_validator("groups")
    @classmethod
    def valid_group_names(
        cls, values: dict[str, ScenarioGroupTemplate]
    ) -> dict[str, ScenarioGroupTemplate]:
        _validate_named_mapping(values, "scenario group")
        return values

    @field_validator("profiles")
    @classmethod
    def valid_profile_names(
        cls, values: dict[str, ScenarioProfileTemplate]
    ) -> dict[str, ScenarioProfileTemplate]:
        _validate_named_mapping(values, "scenario profile")
        return values


class SupervisorOptionsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    priority: int = Field(default=100, ge=0, le=999)
    autorestart: Literal["false", "unexpected", "true"] = "unexpected"
    startsecs: int = Field(default=3, ge=0, le=3600)
    startretries: int = Field(default=3, ge=0, le=100)
    stopsignal: str = Field(default="INT", pattern=r"^[A-Z][A-Z0-9]*$")
    stopasgroup: bool = True
    killasgroup: bool = True
    stopwaitsecs: int = Field(default=15, ge=0, le=3600)


class ScenarioGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: bool = True
    container: str | None = None
    service: str | None = None
    script: str
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    user: str | None = None
    workdir: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    supervisor: SupervisorOptionsSpec = Field(default_factory=SupervisorOptionsSpec)

    @field_validator("script")
    @classmethod
    def script_is_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scenario group script must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, str]) -> dict[str, str]:
        invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid scenario environment variable name(s): {', '.join(invalid)}")
        return values


class TmuxProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["tmux"]
    compose_file: Path | None = None
    project_name: str | None = None
    wait_timeout_seconds: int = Field(default=60, ge=1, le=3600)
    session: str | None = None
    attach: bool = True
    replace: bool = False
    stop_grace_seconds: int = Field(default=5, ge=0, le=30)


class ComposeSupervisorProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["compose-supervisor"]
    compose_file: Path
    project_name: str | None = None
    supervisor_config_dir: Path


@dataclass(frozen=True)
class ScenarioGroupPlan:
    name: str
    container: str | None
    service: str | None
    script: str
    interpreter: tuple[str, ...]
    user: str | None
    workdir: str | None
    environment: tuple[tuple[str, str], ...]
    supervisor: SupervisorOptionsSpec


@dataclass(frozen=True)
class TmuxScenarioPlan:
    scene_name: str
    profile_name: str
    session: str
    attach: bool
    replace: bool
    stop_grace_seconds: int
    groups: tuple[ScenarioGroupPlan, ...]
    compose_file: Path | None = None
    project_name: str | None = None
    wait_timeout_seconds: int = 60


@dataclass(frozen=True)
class ComposeSupervisorPlan:
    scene_name: str
    profile_name: str
    compose_file: Path
    project_name: str
    supervisor_config_dir: Path
    groups: tuple[ScenarioGroupPlan, ...]


ScenarioPlan = TmuxScenarioPlan | ComposeSupervisorPlan


@dataclass(frozen=True)
class ScenarioResult:
    scene_name: str
    profile_name: str
    detail: str = ""
