"""Mutable state that exists only for the lifetime of one menu process."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...config.models import ToolchainConfig


@dataclass
class MenuSession:
    config_path: Path
    config: ToolchainConfig
    values_path: Path | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
