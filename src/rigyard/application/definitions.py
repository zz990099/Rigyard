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

    if not groups:
        template = _legacy_mapping(config, kind).get(name)
        if template is None:
            return None
        return DefinitionMatch(template, config_path.resolve())

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


def definition_source_paths(config: RigyardConfig, config_path: Path) -> dict[str, Path]:
    """Map materialization prefixes to the source file that defined them."""

    paths: dict[str, Path] = {}
    for kind in ("images", "containers", "builds", "tests", "tasks", "scenarios"):
        groups = config.source_files.get(kind, ())
        if groups:
            for group in groups:
                for name in group.definitions:
                    paths.setdefault(f"{kind}.{name}", group.path)
            continue
        for name in _legacy_mapping(config, kind):
            paths[f"{kind}.{name}"] = config_path.resolve()
    return paths


def _resolve_source_path(config_path: Path, source_path: Path) -> Path:
    path = source_path.expanduser()
    if not path.is_absolute():
        path = config_path.resolve().parent / path
    return path.resolve()


def _legacy_mapping(config: RigyardConfig, kind: str) -> dict[str, Any]:
    if kind == "images":
        return config.images
    if kind == "containers":
        return config.containers
    if kind == "builds":
        return config.builds
    if kind == "tests":
        return config.tests
    if kind == "tasks":
        return config.tasks
    return config.scenarios
