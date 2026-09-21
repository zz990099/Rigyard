"""Mutable state that exists only for the lifetime of one menu process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...application.project import ProjectContext


@dataclass
class MenuSession:
    project: ProjectContext
    values_path: Path | None = None

    @property
    def config_path(self) -> Path:
        return self.project.config_path

    @property
    def config(self):
        return self.project.config
