"""Manifest, source-file, and assembled project configuration models."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from ..builds.models import BuildTemplate
from ..containers.models import ContainerTemplate
from ..images.models import IMAGE_NAME, ImageTemplate
from ..scenarios.models import ScenarioTemplate

SCHEMA_VERSION = 3
VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_LOGO_BYTES = 8 * 1024
MAX_LOGO_LINES = 12
MAX_LOGO_COLUMNS = 100


def _invalid_names(values: dict[str, object]) -> list[str]:
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


class RigyardBranding(BaseModel):
    """Optional terminal branding for the interactive menu."""

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


class RigyardSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: Path | tuple[Path, ...] | None = None
    containers: Path | tuple[Path, ...] | None = None
    builds: Path | tuple[Path, ...] | None = None
    scenarios: Path | tuple[Path, ...] | None = None

    @field_validator("images", "containers", "builds", "scenarios")
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
            source is None for source in (self.images, self.containers, self.builds, self.scenarios)
        ):
            raise ValueError("at least one configuration source is required")
        return self


class SourceFileInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    description: str | None = None
    names: tuple[str, ...] = ()
    definitions: dict[str, Any] = Field(default_factory=dict)


class RigyardManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    metadata: RigyardMetadata
    branding: RigyardBranding = Field(default_factory=RigyardBranding)
    sources: RigyardSources
    variables: dict[str, str] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value == SCHEMA_VERSION:
            return value
        if value == 2:
            raise ValueError(
                "schema version 2 is not supported: move scenario `groups` under "
                "`instances.<name>` and set `version: 3`"
            )
        raise ValueError(f"unsupported schema version {value}; expected {SCHEMA_VERSION}")

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, values: dict[str, str]) -> dict[str, str]:
        invalid = sorted(name for name in values if not VARIABLE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid global variable name(s): {', '.join(invalid)}")
        return values


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
    """Fully loaded immutable configuration used by application services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    metadata: RigyardMetadata
    branding: RigyardBranding = Field(default_factory=RigyardBranding)
    sources: RigyardSources
    variables: dict[str, str] = Field(default_factory=dict)
    images: dict[str, ImageTemplate] = Field(default_factory=dict)
    containers: dict[str, ContainerTemplate] = Field(default_factory=dict)
    builds: dict[str, BuildTemplate] = Field(default_factory=dict)
    scenarios: dict[str, ScenarioTemplate] = Field(default_factory=dict)
    source_files: dict[str, tuple[SourceFileInfo, ...]] = Field(default_factory=dict)
    duplicate_names: dict[str, dict[str, tuple[Path, ...]]] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, values: dict[str, str]) -> dict[str, str]:
        invalid = sorted(name for name in values if not VARIABLE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid global variable name(s): {', '.join(invalid)}")
        return values

    @field_validator("images")
    @classmethod
    def valid_image_names(cls, value: dict[str, ImageTemplate]) -> dict[str, ImageTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid image name(s): {', '.join(invalid)}")
        return value

    @field_validator("containers")
    @classmethod
    def valid_container_names(
        cls, value: dict[str, ContainerTemplate]
    ) -> dict[str, ContainerTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid container name(s): {', '.join(invalid)}")
        return value

    @field_validator("builds")
    @classmethod
    def valid_build_names(cls, value: dict[str, BuildTemplate]) -> dict[str, BuildTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid build name(s): {', '.join(invalid)}")
        return value

    @field_validator("scenarios")
    @classmethod
    def valid_scenario_names(
        cls, value: dict[str, ScenarioTemplate]
    ) -> dict[str, ScenarioTemplate]:
        invalid = _invalid_names(value)
        if invalid:
            raise ValueError(f"invalid scenario name(s): {', '.join(invalid)}")
        return value
