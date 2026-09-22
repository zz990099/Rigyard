"""Templates, resolved specs, and immutable plans for named scenarios."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from ..parameters.models import PromptValue

SCENARIO_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

RuntimeText = PromptValue | str
RuntimeBool = PromptValue | StrictBool
RuntimeList = PromptValue | tuple[str, ...]
RuntimeInteger = PromptValue | int
RuntimePath = PromptValue | Path
RestartPolicy = Literal["always", "if_not_running", "never"]
StartupMode = Literal["parallel", "sequential"]
RuntimeStartupMode = PromptValue | StartupMode


def _validate_process_source(
    script: object,
    command: object,
    setup: object,
    label: str,
) -> None:
    if (script is None) == (command is None):
        raise ValueError(f"{label} requires exactly one of script or command")
    for name, values in (("command", command), ("setup", setup)):
        if isinstance(values, tuple) and any(not item for item in values):
            raise ValueError(f"{label} {name} entries must not be empty")


def _validate_named_mapping(values: Mapping[str, object], label: str) -> None:
    invalid = sorted(name for name in values if not SCENARIO_NAME.fullmatch(name))
    if invalid:
        raise ValueError(f"invalid {label} name(s): {', '.join(invalid)}")


class ScenarioGroupTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: RuntimeBool = True
    script: RuntimeText | None = None
    command: RuntimeList | None = None
    setup: RuntimeList = ()
    interpreter: RuntimeList = ("/bin/sh", "-eu")
    user: RuntimeText | None = None
    workdir: RuntimeText | None = None
    environment: dict[str, RuntimeText] = Field(default_factory=dict)

    @field_validator("interpreter")
    @classmethod
    def interpreter_is_not_empty(cls, value: RuntimeList) -> RuntimeList:
        if isinstance(value, tuple) and not value:
            raise ValueError("scenario group interpreter must not be empty")
        return value

    @field_validator("command")
    @classmethod
    def fixed_command_is_not_empty(cls, value: RuntimeList | None) -> RuntimeList | None:
        if isinstance(value, tuple) and not value:
            raise ValueError("scenario group command must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, RuntimeText]) -> dict[str, RuntimeText]:
        invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid scenario environment variable name(s): {', '.join(invalid)}")
        return values

    @model_validator(mode="after")
    def exactly_one_process_source(self) -> ScenarioGroupTemplate:
        _validate_process_source(self.script, self.command, self.setup, "scenario group")
        return self


class ScenarioStartupTemplate(BaseModel):
    """Ordered launch policy for sibling tmux objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: RuntimeStartupMode = "parallel"
    interval_seconds: RuntimeInteger = 0


class ScenarioInstanceTemplate(BaseModel):
    """One software system: one container or Compose service, one tmux window, several panes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: RuntimeBool = True
    container: RuntimeText | None = None
    service: RuntimeText | None = None
    startup: ScenarioStartupTemplate = ScenarioStartupTemplate()
    groups: dict[str, ScenarioGroupTemplate] = Field(min_length=1)

    @model_validator(mode="after")
    def exactly_one_target(self) -> ScenarioInstanceTemplate:
        if (self.container is None) == (self.service is None):
            raise ValueError("scenario instance requires exactly one of container or service")
        return self

    @field_validator("groups")
    @classmethod
    def valid_group_names(
        cls, values: dict[str, ScenarioGroupTemplate]
    ) -> dict[str, ScenarioGroupTemplate]:
        _validate_named_mapping(values, "scenario group")
        return values


class ScenarioProfileTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session: RuntimeText | None = None
    attach: RuntimeBool = True
    stop_grace_seconds: RuntimeInteger = 5
    restart_container: RestartPolicy = "always"
    mouse: bool = True
    keep_alive: bool = True


class ScenarioComposeTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: RuntimePath
    project_name: RuntimeText | None = None
    wait_timeout_seconds: RuntimeInteger = 60
    environment: dict[str, RuntimeText] = Field(default_factory=dict)

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, RuntimeText]) -> dict[str, RuntimeText]:
        invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid Compose environment variable name(s): {', '.join(invalid)}")
        return values


class ScenarioTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    compose: ScenarioComposeTemplate | None = None
    startup: ScenarioStartupTemplate = ScenarioStartupTemplate()
    instances: dict[str, ScenarioInstanceTemplate] = Field(min_length=1)
    profiles: dict[str, ScenarioProfileTemplate] = Field(min_length=1)

    @field_validator("instances")
    @classmethod
    def valid_instance_names(
        cls, values: dict[str, ScenarioInstanceTemplate]
    ) -> dict[str, ScenarioInstanceTemplate]:
        _validate_named_mapping(values, "scenario instance")
        return values

    @field_validator("profiles")
    @classmethod
    def valid_profile_names(
        cls, values: dict[str, ScenarioProfileTemplate]
    ) -> dict[str, ScenarioProfileTemplate]:
        _validate_named_mapping(values, "scenario profile")
        return values

    @model_validator(mode="after")
    def targets_match_compose_mode(self) -> ScenarioTemplate:
        for name, instance in self.instances.items():
            if self.compose is None:
                if instance.service is not None:
                    raise ValueError(
                        f"scenario instance {name!r} uses service but scenario has no compose; "
                        "use container instead"
                    )
            elif instance.container is not None:
                raise ValueError(
                    f"scenario instance {name!r} uses container for a Compose-managed scenario; "
                    "use service instead"
                )
        return self


class ScenarioGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: bool = True
    script: str | None = None
    command: tuple[str, ...] | None = None
    setup: tuple[str, ...] = ()
    interpreter: tuple[str, ...] = Field(default=("/bin/sh", "-eu"), min_length=1)
    user: str | None = None
    workdir: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)

    @field_validator("script")
    @classmethod
    def script_is_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("scenario group script must not be empty")
        return value

    @field_validator("command")
    @classmethod
    def command_is_not_empty(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and not value:
            raise ValueError("scenario group command must not be empty")
        return value

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, str]) -> dict[str, str]:
        invalid = sorted(name for name in values if not ENVIRONMENT_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid scenario environment variable name(s): {', '.join(invalid)}")
        return values

    @model_validator(mode="after")
    def exactly_one_process_source(self) -> ScenarioGroupSpec:
        _validate_process_source(self.script, self.command, self.setup, "scenario group")
        return self


class ScenarioStartupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: StartupMode = "parallel"
    interval_seconds: int = Field(default=0, ge=0, le=3600)


class ScenarioInstanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = None
    enabled: bool = True
    container: str | None = None
    service: str | None = None
    startup: ScenarioStartupSpec = ScenarioStartupSpec()
    groups: dict[str, ScenarioGroupSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def exactly_one_target(self) -> ScenarioInstanceSpec:
        if (self.container is None) == (self.service is None):
            raise ValueError("scenario instance requires exactly one of container or service")
        return self


class ScenarioProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session: str | None = None
    attach: bool = True
    stop_grace_seconds: int = Field(default=5, ge=0, le=30)
    restart_container: RestartPolicy = "always"
    mouse: bool = True
    keep_alive: bool = True


class ScenarioComposeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: Path
    project_name: str | None = None
    wait_timeout_seconds: int = Field(default=60, ge=1, le=3600)
    environment: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioGroupPlan:
    name: str
    script: str | None
    interpreter: tuple[str, ...]
    user: str | None
    workdir: str | None
    environment: tuple[tuple[str, str], ...]
    command: tuple[str, ...] | None = None
    setup: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioStartupPlan:
    mode: StartupMode = "parallel"
    interval_seconds: int = 0


@dataclass(frozen=True)
class ScenarioInstancePlan:
    name: str
    container: str | None
    groups: tuple[ScenarioGroupPlan, ...]
    service: str | None = None
    startup: ScenarioStartupPlan = ScenarioStartupPlan()


@dataclass(frozen=True)
class ScenarioComposePlan:
    file: Path
    project_name: str
    wait_timeout_seconds: int
    environment: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScenarioPlan:
    scene_name: str
    profile_name: str
    session: str
    attach: bool
    stop_grace_seconds: int
    instances: tuple[ScenarioInstancePlan, ...]
    compose: ScenarioComposePlan | None = None
    restart_container: RestartPolicy = "always"
    mouse: bool = True
    keep_alive: bool = True
    partial: bool = False
    startup: ScenarioStartupPlan = ScenarioStartupPlan()


@dataclass(frozen=True)
class ScenarioResult:
    scene_name: str
    profile_name: str
    detail: str = ""
