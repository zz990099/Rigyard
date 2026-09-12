"""Configuration models for inline runtime prompts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class PromptMode(str, Enum):
    INPUT = "input"
    CONFIRM = "confirm"
    SELECT = "select"


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: PromptMode
    message: str
    options: tuple[Any, ...] | None = None
    repeat: bool = False
    item_hint: str | None = None

    @model_validator(mode="after")
    def validate_mode_options(self) -> PromptSpec:
        if not self.message.strip():
            raise ValueError("prompt message must not be empty")
        if self.mode == PromptMode.SELECT:
            if not self.options:
                raise ValueError("select prompts require non-empty options")
            if self.repeat:
                raise ValueError("select prompts do not support repeat")
        elif self.options is not None:
            raise ValueError("options is only valid for select prompts")
        if self.repeat and self.mode != PromptMode.INPUT:
            raise ValueError("repeat is only valid for input prompts")
        return self


class PromptValue(BaseModel):
    """A value acquired when its containing feature is selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default: Any = None
    prompt: PromptSpec

    @model_validator(mode="after")
    def default_matches_prompt(self) -> PromptValue:
        if "default" not in self.model_fields_set:
            return self
        if self.prompt.mode == PromptMode.CONFIRM and not isinstance(self.default, bool):
            raise ValueError("confirm prompt default must be a boolean")
        if self.prompt.mode == PromptMode.SELECT and self.default not in (
            self.prompt.options or ()
        ):
            raise ValueError("select prompt default must be one of its options")
        if self.prompt.repeat and not isinstance(self.default, (list, tuple)):
            raise ValueError("repeated input prompt default must be a list")
        return self

    @property
    def has_default(self) -> bool:
        return "default" in self.model_fields_set
