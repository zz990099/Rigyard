"""Source-qualified resource lookup over the loaded configuration snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ..errors import SchemaValidationError

if TYPE_CHECKING:
    from .models import RigyardConfig, SourceFileInfo

RESOURCE_KINDS = ("images", "containers", "builds", "tests", "tasks", "scenarios")


@dataclass(frozen=True)
class Definition:
    kind: str
    name: str
    source_path: Path
    value: BaseModel

    @property
    def prefix(self) -> str:
        return f"{self.kind}.{self.name}"


class DefinitionCatalog:
    """Use source definitions as authority; top-level mappings are compatibility views."""

    def __init__(self, config: RigyardConfig, config_path: Path) -> None:
        self.config = config
        self.config_path = config_path.resolve()
        entries: list[Definition] = []
        for kind in RESOURCE_KINDS:
            groups = self.groups(kind)
            if groups:
                entries.extend(
                    Definition(kind, name, group.path, value)
                    for group in groups
                    for name, value in group.definitions.items()
                )
            else:
                entries.extend(
                    Definition(kind, name, self.config_path, value)
                    for name, value in getattr(config, kind).items()
                )
        self.entries = tuple(entries)

    def groups(self, kind: str) -> tuple[SourceFileInfo, ...]:
        return self.config.source_files.get(kind, ())

    def source(self, path: Path) -> Path:
        expanded = path.expanduser()
        return (self.config_path.parent / expanded).resolve()

    def find(self, kind: str, name: str, source: Path | None = None) -> Definition | None:
        candidates = [item for item in self.entries if item.kind == kind and item.name == name]
        if source is not None:
            target = self.source(source)
            if target not in {group.path for group in self.groups(kind)}:
                raise SchemaValidationError(f"unknown {kind} source {target}")
            candidates = [item for item in candidates if item.source_path == target]
            if not candidates:
                raise SchemaValidationError(f"unknown {kind[:-1]} {name!r} in source {target}")
        if len(candidates) > 1:
            paths = ", ".join(str(item.source_path) for item in candidates)
            raise SchemaValidationError(
                f"ambiguous {kind[:-1]} {name!r}; defined in {paths}; select --source"
            )
        return candidates[0] if candidates else None

    def selected(self, source: Path | None = None) -> tuple[Definition, ...]:
        """Select an unambiguous set for project-wide inspect and resolve commands."""
        entries = self.entries
        if source is not None:
            target = self.source(source)
            if target not in {group.path for kind in RESOURCE_KINDS for group in self.groups(kind)}:
                raise SchemaValidationError(f"unknown configuration source {target}")
            entries = tuple(item for item in entries if item.source_path == target)
        seen: set[str] = set()
        for item in entries:
            if item.prefix in seen:
                raise SchemaValidationError(f"ambiguous {item.prefix!r}; select --source")
            seen.add(item.prefix)
        return entries
