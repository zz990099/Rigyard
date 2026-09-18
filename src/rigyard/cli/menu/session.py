"""Mutable state that exists only for the lifetime of one menu process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...config.models import RigyardConfig


@dataclass
class MenuSession:
    config_path: Path
    config: RigyardConfig
    values_path: Path | None = None
