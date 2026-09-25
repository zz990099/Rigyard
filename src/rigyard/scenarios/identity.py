"""Stable identity shared by scenario runtime resources and persisted records."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScenarioIdentity:
    config_path: Path
    source_path: Path
    scene_name: str
    profile_name: str

    @property
    def key(self) -> str:
        value = json.dumps(
            [
                str(self.config_path.resolve()),
                str(self.source_path.resolve()),
                self.scene_name,
                self.profile_name,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode()).hexdigest()

    def runtime_name(self, project_name: str) -> str:
        slug = re.sub(
            r"[^a-z0-9_-]+",
            "-",
            f"{project_name}-{self.scene_name}-{self.profile_name}".lower(),
        ).strip("-")
        return f"rigyard-{slug[:40] or 'scene'}-{self.key[:12]}"
