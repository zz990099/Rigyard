"""Immutable inputs shared by command and menu frontends."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..immutable import freeze
from .project import ProjectContext

InputFunction = Callable[[str], str]


@dataclass(frozen=True)
class ResolutionRequest:
    config_path: Path
    values_path: Path | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)
    interactive: bool = True
    input_fn: InputFunction = input
    source_path: Path | None = None
    project: ProjectContext | None = None
    workspace_root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        if self.values_path is not None:
            object.__setattr__(self, "values_path", Path(self.values_path))
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))
        if self.workspace_root is not None:
            object.__setattr__(self, "workspace_root", Path(self.workspace_root))
        object.__setattr__(self, "overrides", freeze(self.overrides))


@dataclass(frozen=True)
class BuildImageRequest:
    config_path: Path
    image_name: str
    values_path: Path | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)
    interactive: bool = True
    input_fn: InputFunction = input
    source_path: Path | None = None
    project: ProjectContext | None = None
    workspace_root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        if self.values_path is not None:
            object.__setattr__(self, "values_path", Path(self.values_path))
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))
        if self.workspace_root is not None:
            object.__setattr__(self, "workspace_root", Path(self.workspace_root))
        object.__setattr__(self, "overrides", freeze(self.overrides))

    def resolution_request(self) -> ResolutionRequest:
        return ResolutionRequest(
            config_path=self.config_path,
            values_path=self.values_path,
            overrides=self.overrides,
            interactive=self.interactive,
            input_fn=self.input_fn,
            source_path=self.source_path,
            project=self.project,
            workspace_root=self.workspace_root,
        )
