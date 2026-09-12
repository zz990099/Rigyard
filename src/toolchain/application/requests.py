"""Immutable inputs shared by command and menu frontends."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

InputFunction = Callable[[str], str]


@dataclass(frozen=True)
class ResolutionRequest:
    config_path: Path
    values_path: Path | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)
    interactive: bool = True
    input_fn: InputFunction = input

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        if self.values_path is not None:
            object.__setattr__(self, "values_path", Path(self.values_path))
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))


@dataclass(frozen=True)
class BuildImageRequest:
    config_path: Path
    image_name: str
    values_path: Path | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)
    interactive: bool = True
    input_fn: InputFunction = input

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        if self.values_path is not None:
            object.__setattr__(self, "values_path", Path(self.values_path))
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))

    def resolution_request(self) -> ResolutionRequest:
        return ResolutionRequest(
            self.config_path,
            self.values_path,
            self.overrides,
            self.interactive,
            self.input_fn,
        )
