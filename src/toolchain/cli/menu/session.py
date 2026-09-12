"""Mutable state that exists only for the lifetime of one menu process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...config.models import ToolchainConfig


@dataclass
class MenuSession:
    config_path: Path
    config: ToolchainConfig
    values_path: Path | None = None
