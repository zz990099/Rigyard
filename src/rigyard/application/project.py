"""A stable project snapshot shared across one frontend operation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))

    @classmethod
    def capture(
        cls,
        config_path: str | Path,
        *,
        config: RigyardConfig | None = None,
        environment: Mapping[str, str] | None = None,
        timestamp: datetime | None = None,
    ) -> ProjectContext:
        path = Path(config_path)
        return cls(
            config_path=path,
            config=load_config(path) if config is None else config,
            environment=os.environ if environment is None else environment,
            timestamp=datetime.now().astimezone() if timestamp is None else timestamp,
        )


def project_context(
    config_path: str | Path,
    current: ProjectContext | None,
    *,
    environment: Mapping[str, str] | None = None,
    timestamp: datetime | None = None,
) -> ProjectContext:
    """Reuse a supplied snapshot while honoring explicit test/runtime overrides."""

    if current is None:
        return ProjectContext.capture(
            config_path,
            environment=environment,
            timestamp=timestamp,
        )
    if environment is None and timestamp is None:
        return current
    return ProjectContext(
        config_path=current.config_path,
        config=current.config,
        environment=current.environment if environment is None else environment,
        timestamp=current.timestamp if timestamp is None else timestamp,
    )
