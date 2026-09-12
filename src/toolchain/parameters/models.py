"""Pydantic models for the YAML v1 parameter schema."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .conditions import ConditionData, validate_condition

PARAMETER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class ParameterType(str, Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    PATH = "path"
    LIST = "list"


class ParameterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: ParameterType = ParameterType.STRING
    description: str | None = None
    default: Any = None
    required: bool = False
    enabled_if: ConditionData | None = None
    required_if: ConditionData | None = None
    options: tuple[Any, ...] | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    must_exist: bool = False
    item_type: ParameterType | None = None

    @field_validator("enabled_if", "required_if")
    @classmethod
    def condition_is_structured(cls, value: ConditionData | None) -> ConditionData | None:
        if value is not None:
            validate_condition(value)
        return value

    @field_validator("pattern")
    @classmethod
    def pattern_is_valid(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regular expression: {exc}") from exc
        return value

    @model_validator(mode="after")
    def fields_match_type(self) -> ParameterSpec:
        if self.type == ParameterType.CHOICE:
            if not self.options:
                raise ValueError("choice parameters require a non-empty options list")
        elif self.options is not None:
            raise ValueError("options is only valid for choice parameters")

        if self.item_type is not None and self.type != ParameterType.LIST:
            raise ValueError("item_type is only valid for list parameters")
        if self.item_type == ParameterType.LIST:
            raise ValueError("nested list item_type is not supported in schema v1")
        if self.must_exist and self.type != ParameterType.PATH:
            raise ValueError("must_exist is only valid for path parameters")
        if self.pattern is not None and self.type != ParameterType.STRING:
            raise ValueError("pattern is only valid for string parameters")
        if (self.min is not None or self.max is not None) and self.type not in {
            ParameterType.INT,
            ParameterType.FLOAT,
            ParameterType.LIST,
        }:
            raise ValueError("min/max are only valid for int, float, and list parameters")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min cannot be greater than max")
        if self.type == ParameterType.LIST:
            for field_name, value in (("min", self.min), ("max", self.max)):
                if value is not None and not value.is_integer():
                    raise ValueError(f"{field_name} must be a whole number for list parameters")
        return self


class ParameterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(strict=True)
    parameters: dict[str, ParameterSpec]

    @field_validator("version")
    @classmethod
    def only_version_one(cls, value: int) -> int:
        if value != 1:
            raise ValueError("only schema version 1 is supported")
        return value

    @field_validator("parameters")
    @classmethod
    def parameter_names_are_valid(
        cls, value: dict[str, ParameterSpec]
    ) -> dict[str, ParameterSpec]:
        for name in value:
            if not PARAMETER_NAME.fullmatch(name):
                raise ValueError(
                    f"invalid parameter name {name!r}; expected {PARAMETER_NAME.pattern}"
                )
        return value
