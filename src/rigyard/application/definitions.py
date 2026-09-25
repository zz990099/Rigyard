"""Application access to the canonical source-qualified definition catalog."""

from __future__ import annotations

from pathlib import Path

from ..config.catalog import Definition, DefinitionCatalog
from ..config.models import RigyardConfig


def find_definition(
    config: RigyardConfig,
    kind: str,
    name: str,
    source_path: Path | None,
    config_path: Path,
) -> Definition | None:
    return DefinitionCatalog(config, config_path).find(kind, name, source_path)


def definition_source_paths(
    config: RigyardConfig,
    config_path: Path,
    source_path: Path | None = None,
) -> dict[str, Path]:
    return {
        item.prefix: item.source_path
        for item in DefinitionCatalog(config, config_path).selected(source_path)
    }
