"""Dynamic candidate sources for select prompts.

The configuration only names a provider (plus its filter); the candidates are
looked up on the host when a prompt is actually shown, so the parameter layer
stays independent of any concrete tool.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, field_validator

PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class DynamicOption:
    """One candidate offered by a dynamic source."""

    value: str
    label: str | None = None


DynamicOptionsProvider = Callable[["PromptSource"], Sequence[DynamicOption]]
DynamicSources = Mapping[str, DynamicOptionsProvider]


class PromptSource(BaseModel):
    """Runtime source of the candidate list for one select prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    filter: str | None = None
    running_only: bool = False

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value: str) -> str:
        if not PROVIDER_NAME.fullmatch(value):
            raise ValueError(f"invalid provider name {value!r}")
        return value

    @field_validator("filter")
    @classmethod
    def valid_filter(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid filter regex {value!r}: {exc}") from exc
        return value
