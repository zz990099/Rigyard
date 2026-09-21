"""Manifest, source-file, and assembled project configuration models."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from ..builds.models import BuildTemplate
from ..containers.models import ContainerTemplate
from ..images.models import IMAGE_NAME, ImageTemplate
from ..scenarios.models import ScenarioTemplate
from ..tasks.models import TaskTemplate
from ..tests.models import TestTemplate

SCHEMA_VERSION = 3
VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMMAND_ALIAS_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
MAX_LOGO_BYTES = 8 * 1024
MAX_LOGO_LINES = 12
MAX_LOGO_COLUMNS = 100
ValueT = TypeVar("ValueT")


def _freeze_mapping(values: Mapping[str, ValueT]) -> Mapping[str, ValueT]:
    return MappingProxyType(dict(values))


def _invalid_names(values: Mapping[str, object]) -> list[str]:
    return sorted(name for name in values if not IMAGE_NAME.fullmatch(name))


def _display_width(value: str) -> int:
    return sum(
        0
        if unicodedata.combining(character)
        else 2
        if unicodedata.east_asian_width(character) in {"F", "W"}
        else 1
        for character in value
    )


class RigyardMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_is_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("metadata.name must not be empty")
        return value


class RigyardWorkspace(BaseModel):
    """Optional defaults applied by ``rigyard init``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_alias: str | None = None

    @field_validator("command_alias")
    @classmethod
    def valid_command_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not COMMAND_ALIAS_NAME.fullmatch(value) or value == "rigyard":
            raise ValueError(
                "workspace.command_alias must be a non-reserved name containing "
                "letters, digits, '_' or '-'"
            )
        return value


class RigyardBranding(BaseModel):
    """Resolved terminal branding used by the interactive menu."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logo: str | None = None

    @field_validator("logo")
    @classmethod
    def valid_terminal_logo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        logo = value.rstrip("\r\n")
        if not logo.strip():
            raise ValueError("branding.logo must not be empty")
        if len(logo.encode("utf-8")) > MAX_LOGO_BYTES:
            raise ValueError(f"branding.logo must not exceed {MAX_LOGO_BYTES} UTF-8 bytes")
        if any(
            character != "\n" and unicodedata.category(character).startswith("C")
            for character in logo
        ):
            raise ValueError("branding.logo must not contain control characters")
        lines = logo.split("\n")
        if len(lines) > MAX_LOGO_LINES:
            raise ValueError(f"branding.logo must not exceed {MAX_LOGO_LINES} lines")
        if any(_display_width(line) > MAX_LOGO_COLUMNS for line in lines):
            raise ValueError(
                f"branding.logo lines must not exceed {MAX_LOGO_COLUMNS} display columns"
            )
        return logo


class RigyardBrandingSource(RigyardBranding):
    """Terminal branding as declared in the root manifest."""

    logo_file: Path | None = None

    @field_validator("logo_file", mode="before")
    @classmethod
    def logo_file_is_not_empty(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("branding.logo_file must not be empty")
        return value

    @model_validator(mode="after")
    def one_logo_source(self) -> RigyardBrandingSource:
        if self.logo is not None and self.logo_file is not None:
            raise ValueError("branding.logo and branding.logo_file are mutually exclusive")
        return self


class RigyardSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: Path | tuple[Path, ...] | None = None
    containers: Path | tuple[Path, ...] | None = None
    builds: Path | tuple[Path, ...] | None = None
    tests: Path | tuple[Path, ...] | None = None
    tasks: Path | tuple[Path, ...] | None = None
    scenarios: Path | tuple[Path, ...] | None = None

    @field_validator("images", "containers", "builds", "tests", "tasks", "scenarios")
    @classmethod
    def source_list_is_not_empty(
        cls, value: Path | tuple[Path, ...] | None
    ) -> Path | tuple[Path, ...] | None:
        if value == ():
            raise ValueError("source list must not be empty")
        return value

    @model_validator(mode="after")
    def at_least_one_source(self) -> RigyardSources:
        if all(
            source is None
            for source in (
                self.images,
                self.containers,
                self.builds,
                self.tests,
                self.tasks,
                self.scenarios,
            )
        ):
            raise ValueError("at least one configuration source is required")
        return self


class SourceFileInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    path: Path
    description: str | None = None
    names: tuple[str, ...] = ()
    definitions: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("definitions")
    @classmethod
    def frozen_definitions(cls, values: Mapping[str, Any]) -> Mapping[str, Any]:
        return _freeze_mapping(values)


class RigyardManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    version: int
    metadata: RigyardMetadata
    workspace: RigyardWorkspace = Field(default_factory=RigyardWorkspace)
    branding: RigyardBrandingSource = Field(default_factory=RigyardBrandingSource)
    sources: RigyardSources
    variables: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version {value}; expected {SCHEMA_VERSION}")
        return value

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, values: Mapping[str, str]) -> Mapping[str, str]:
        invalid = sorted(name for name in values if not VARIABLE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid global variable name(s): {', '.join(invalid)}")
        return _freeze_mapping(values)


class ImageDefinitions(RootModel[dict[str, ImageTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, ImageTemplate]) -> dict[str, ImageTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid image name(s): {', '.join(invalid)}")
        return value


class ContainerDefinitions(RootModel[dict[str, ContainerTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, ContainerTemplate]) -> dict[str, ContainerTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid container name(s): {', '.join(invalid)}")
        return value


class BuildDefinitions(RootModel[dict[str, BuildTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, BuildTemplate]) -> dict[str, BuildTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid build name(s): {', '.join(invalid)}")
        return value


class TestDefinitions(RootModel[dict[str, TestTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, TestTemplate]) -> dict[str, TestTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid test name(s): {', '.join(invalid)}")
        return value


class TaskDefinitions(RootModel[dict[str, TaskTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, TaskTemplate]) -> dict[str, TaskTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid task name(s): {', '.join(invalid)}")
        return value


class ScenarioDefinitions(RootModel[dict[str, ScenarioTemplate]]):
    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def valid_names(cls, value: dict[str, ScenarioTemplate]) -> dict[str, ScenarioTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid scenario name(s): {', '.join(invalid)}")
        return value


class RigyardConfig(BaseModel):
    """Fully loaded configuration with read-only resource mappings for application services."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    version: int
    metadata: RigyardMetadata
    workspace: RigyardWorkspace = Field(default_factory=RigyardWorkspace)
    branding: RigyardBranding = Field(default_factory=RigyardBranding)
    sources: RigyardSources
    variables: Mapping[str, str] = Field(default_factory=dict)
    images: Mapping[str, ImageTemplate] = Field(default_factory=dict)
    containers: Mapping[str, ContainerTemplate] = Field(default_factory=dict)
    builds: Mapping[str, BuildTemplate] = Field(default_factory=dict)
    tests: Mapping[str, TestTemplate] = Field(default_factory=dict)
    tasks: Mapping[str, TaskTemplate] = Field(default_factory=dict)
    scenarios: Mapping[str, ScenarioTemplate] = Field(default_factory=dict)
    source_files: Mapping[str, tuple[SourceFileInfo, ...]]
    duplicate_names: Mapping[str, Mapping[str, tuple[Path, ...]]] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, values: Mapping[str, str]) -> Mapping[str, str]:
        invalid = sorted(name for name in values if not VARIABLE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid global variable name(s): {', '.join(invalid)}")
        return _freeze_mapping(values)

    @field_validator("images", "containers", "builds", "tests", "tasks", "scenarios")
    @classmethod
    def valid_definition_names(cls, values: Mapping[str, Any]) -> Mapping[str, Any]:
        invalid = _invalid_names(values)
        if invalid:
            raise ValueError(f"invalid definition name(s): {', '.join(invalid)}")
        return _freeze_mapping(values)

    @field_validator("source_files")
    @classmethod
    def frozen_source_files(
        cls, values: Mapping[str, tuple[SourceFileInfo, ...]]
    ) -> Mapping[str, tuple[SourceFileInfo, ...]]:
        return _freeze_mapping(values)

    @field_validator("duplicate_names")
    @classmethod
    def frozen_duplicate_names(
        cls, values: Mapping[str, Mapping[str, tuple[Path, ...]]]
    ) -> Mapping[str, Mapping[str, tuple[Path, ...]]]:
        return _freeze_mapping(
            {kind: _freeze_mapping(duplicates) for kind, duplicates in values.items()}
        )
