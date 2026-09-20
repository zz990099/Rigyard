"""Configuration models for inline runtime prompts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from .sources import PromptSource


class PromptMode(str, Enum):
    INPUT = "input"
    CONFIRM = "confirm"
    SELECT = "select"


class PromptMerge(str, Enum):
    REPLACE = "replace"
    APPEND = "append"


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: PromptMode
    message: str
    options: tuple[Any, ...] | None = None
    source: PromptSource | None = None
    repeat: bool = False
    item_hint: str | None = None
    merge: PromptMerge = PromptMerge.REPLACE
    input_template: str | None = None

    @model_validator(mode="after")
    def validate_mode_options(self) -> PromptSpec:
        if not self.message.strip():
            raise ValueError("prompt message must not be empty")
        if self.mode == PromptMode.SELECT:
            if self.source is None and not self.options:
                raise ValueError("select prompts require non-empty options or a source")
            if self.source is not None and self.options is not None:
                raise ValueError("select prompts accept options or a source, not both")
            if self.repeat:
                raise ValueError("select prompts do not support repeat")
        elif self.options is not None or self.source is not None:
            raise ValueError("options and source are only valid for select prompts")
        if self.repeat and self.mode != PromptMode.INPUT:
            raise ValueError("repeat is only valid for input prompts")
        if self.merge != PromptMerge.REPLACE and self.mode != PromptMode.INPUT:
            raise ValueError("merge is only configurable for input prompts")
        if self.input_template is not None:
            if self.mode != PromptMode.INPUT:
                raise ValueError("input_template is only valid for input prompts")
            if "$${INPUT}" in self.input_template:
                raise ValueError("input_template cannot escape the ${INPUT} placeholder")
            if self.input_template.count("${INPUT}") != 1:
                raise ValueError("input_template must contain ${INPUT} exactly once")
        return self


class PromptValue(BaseModel):
    """A value acquired when its containing feature is selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base: Any = None
    default: Any = None
    prompt: PromptSpec

    @model_validator(mode="after")
    def default_matches_prompt(self) -> PromptValue:
        has_base = "base" in self.model_fields_set
        if self.prompt.merge == PromptMerge.APPEND:
            if not has_base:
                raise ValueError("append prompts require a base list")
            if not isinstance(self.base, (list, tuple)):
                raise ValueError("append prompt base must be a list")
        elif has_base:
            raise ValueError("base is only valid when prompt.merge is append")
        if "default" not in self.model_fields_set:
            return self
        if self.prompt.mode == PromptMode.CONFIRM and not isinstance(self.default, bool):
            raise ValueError("confirm prompt default must be a boolean")
        if (
            self.prompt.mode == PromptMode.SELECT
            and self.prompt.source is None
            and self.default not in (self.prompt.options or ())
        ):
            raise ValueError("select prompt default must be one of its options")
        if self.prompt.repeat and not isinstance(self.default, (list, tuple)):
            raise ValueError("repeated input prompt default must be a list")
        return self

    @property
    def has_default(self) -> bool:
        return "default" in self.model_fields_set
