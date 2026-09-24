"""A stable project snapshot shared across one frontend operation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from ..config.loader import load_config
from ..config.models import RigyardConfig


@dataclass(frozen=True)
class ProjectContext:
    """Configuration and host context captured together at one point in time."""

    config_path: Path
    config: RigyardConfig
    environment: Mapping[str, str]
    timestamp: datetime
    workspace_root: Path = field(default_factory=lambda: Path.cwd().resolve())

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).resolve())
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))

    @classmethod
    def capture(
        cls,
        config_path: str | Path,
        *,
        config: RigyardConfig | None = None,
        environment: Mapping[str, str] | None = None,
        timestamp: datetime | None = None,
        workspace_root: str | Path | None = None,
    ) -> ProjectContext:
        path = Path(config_path)
        root = Path.cwd().resolve() if workspace_root is None else Path(workspace_root).resolve()
        return cls(
            config_path=path,
            config=load_config(path, workspace_root=root) if config is None else config,
            environment=os.environ if environment is None else environment,
            timestamp=datetime.now().astimezone() if timestamp is None else timestamp,
            workspace_root=root,
        )


def project_context(
    config_path: str | Path,
    current: ProjectContext | None,
    *,
    environment: Mapping[str, str] | None = None,
    timestamp: datetime | None = None,
    workspace_root: str | Path | None = None,
) -> ProjectContext:
    """Reuse a supplied snapshot while honoring explicit test/runtime overrides."""

    if current is None:
        return ProjectContext.capture(
            config_path,
            environment=environment,
            timestamp=timestamp,
            workspace_root=workspace_root,
        )
    if environment is None and timestamp is None and workspace_root is None:
        return current
    return ProjectContext(
        config_path=current.config_path,
        config=current.config,
        environment=current.environment if environment is None else environment,
        timestamp=current.timestamp if timestamp is None else timestamp,
        workspace_root=current.workspace_root if workspace_root is None else Path(workspace_root),
    )
