"""Resolve a definition by name, optionally scoped to one source file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.models import RigyardConfig
from ..errors import SchemaValidationError


def find_definition(
    config: RigyardConfig,
    kind: str,
    name: str,
    source_path: Path | None,
    config_path: Path,
) -> Any | None:
    """Return one configured definition or ``None`` when the name is unknown."""

    groups = config.source_files.get(kind, ())
    if source_path is not None:
        target = _resolve_source_path(config_path, source_path)
        for group in groups:
            if group.path == target:
                template = group.definitions.get(name)
                if template is None:
                    raise SchemaValidationError(
                        f"unknown {kind[:-1]} {name!r} in source {target}"
                    )
                return template
        available = ", ".join(str(group.path) for group in groups) or "none"
        raise SchemaValidationError(
            f"unknown {kind} source {target}; configured sources: {available}"
        )

    if not groups:
        return _legacy_mapping(config, kind).get(name)

    matches = [
        (group, group.definitions[name])
        for group in groups
        if name in group.definitions
    ]
    if len(matches) > 1:
        paths = ", ".join(str(group.path) for group, _ in matches)
        raise SchemaValidationError(
            f"ambiguous {kind[:-1]} {name!r}; defined in {paths}; select --source"
        )
    if matches:
        return matches[0][1]
    return None


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
    return config.scenarios
