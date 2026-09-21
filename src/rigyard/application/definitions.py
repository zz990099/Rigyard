"""Resolve a definition by name, optionally scoped to one source file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.models import RigyardConfig
from ..errors import SchemaValidationError


@dataclass(frozen=True)
class DefinitionMatch:
    value: Any
    source_path: Path


def find_definition(
    config: RigyardConfig,
    kind: str,
    name: str,
    source_path: Path | None,
    config_path: Path,
) -> DefinitionMatch | None:
    """Return one configured definition or ``None`` when the name is unknown."""

    groups = config.source_files.get(kind, ())
    if source_path is not None:
        target = _resolve_source_path(config_path, source_path)
        for group in groups:
            if group.path == target:
                template = group.definitions.get(name)
                if template is None:
                    raise SchemaValidationError(f"unknown {kind[:-1]} {name!r} in source {target}")
                return DefinitionMatch(template, group.path)
        available = ", ".join(str(group.path) for group in groups) or "none"
        raise SchemaValidationError(
            f"unknown {kind} source {target}; configured sources: {available}"
        )

    matches = [(group, group.definitions[name]) for group in groups if name in group.definitions]
    if len(matches) > 1:
        paths = ", ".join(str(group.path) for group, _ in matches)
        raise SchemaValidationError(
            f"ambiguous {kind[:-1]} {name!r}; defined in {paths}; select --source"
        )
    if matches:
        group, template = matches[0]
        return DefinitionMatch(template, group.path)
    return None


def definition_source_paths(config: RigyardConfig) -> dict[str, Path]:
    """Map materialization prefixes to the source file that defined them."""

    paths: dict[str, Path] = {}
    for kind in ("images", "containers", "builds", "tests", "tasks", "scenarios"):
        for group in config.source_files[kind]:
            for name in group.definitions:
                paths.setdefault(f"{kind}.{name}", group.path)
    return paths


def _resolve_source_path(config_path: Path, source_path: Path) -> Path:
    path = source_path.expanduser()
    if not path.is_absolute():
        path = config_path.resolve().parent / path
    return path.resolve()
