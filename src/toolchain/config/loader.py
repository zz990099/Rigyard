"""Load a v2 project manifest and its referenced YAML configuration sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError
from yaml.nodes import MappingNode, Node, SequenceNode

from ..errors import ConfigIOError, SchemaValidationError, SourceLocation
from .models import (
    BuildDefinitions,
    ContainerDefinitions,
    ImageDefinitions,
    ScenarioDefinitions,
    ToolchainConfig,
    ToolchainManifest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def _locations(node: Node, prefix: tuple[Any, ...] = ()) -> dict[tuple[Any, ...], tuple[int, int]]:
    result = {prefix: (node.start_mark.line + 1, node.start_mark.column + 1)}
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            key = key_node.value
            child = prefix + (key,)
            result[child] = (key_node.start_mark.line + 1, key_node.start_mark.column + 1)
            result.update(_locations(value_node, child))
    elif isinstance(node, SequenceNode):
        for index, value_node in enumerate(node.value):
            result.update(_locations(value_node, prefix + (index,)))
    return result


def _read_yaml(path: str | Path) -> tuple[Any, dict[tuple[Any, ...], tuple[int, int]]]:
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigIOError(str(exc), SourceLocation(file_path)) from exc

    try:
        data = yaml.safe_load(text)
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = SourceLocation(
            file_path,
            mark.line + 1 if mark else None,
            mark.column + 1 if mark else None,
        )
        problem = exc.problem if hasattr(exc, "problem") else exc
        raise ConfigIOError(f"invalid YAML: {problem}", location) from exc
    locations = _locations(root) if root is not None else {}
    return data, locations


def _nearest_location(
    path: Path,
    locations: dict[tuple[Any, ...], tuple[int, int]],
    error_path: tuple[Any, ...],
) -> SourceLocation:
    candidate = error_path
    while candidate not in locations and candidate:
        candidate = candidate[:-1]
    line, column = locations.get(candidate, (None, None))
    return SourceLocation(path, line, column)


def _validate_file(path: Path, model: type[ModelT], *, label: str) -> ModelT:
    data, locations = _read_yaml(path)
    if data is None:
        raise SchemaValidationError(f"{label} must not be empty", SourceLocation(path))
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        error_path = tuple(first.get("loc", ()))
        location = _nearest_location(path, locations, error_path)
        dotted = ".".join(str(part) for part in error_path)
        prefix = f"{dotted}: " if dotted else ""
        raise SchemaValidationError(f"{prefix}{first['msg']}", location) from exc


def _source_path(manifest_path: Path, configured: Path) -> Path:
    source = configured.expanduser()
    if not source.is_absolute():
        source = manifest_path.parent / source
    return source.resolve()


def load_config(path: str | Path) -> ToolchainConfig:
    manifest_path = Path(path).resolve()
    manifest = _validate_file(manifest_path, ToolchainManifest, label="manifest")
    images: dict[str, Any] = {}
    containers: dict[str, Any] = {}
    builds: dict[str, Any] = {}
    scenarios: dict[str, Any] = {}
    if manifest.sources.images is not None:
        source = _source_path(manifest_path, manifest.sources.images)
        images = _validate_file(source, ImageDefinitions, label="image source").root
    if manifest.sources.containers is not None:
        source = _source_path(manifest_path, manifest.sources.containers)
        containers = _validate_file(source, ContainerDefinitions, label="container source").root
    if manifest.sources.builds is not None:
        source = _source_path(manifest_path, manifest.sources.builds)
        builds = _validate_file(source, BuildDefinitions, label="build source").root
    if manifest.sources.scenarios is not None:
        source = _source_path(manifest_path, manifest.sources.scenarios)
        scenarios = _validate_file(source, ScenarioDefinitions, label="scenario source").root
    return ToolchainConfig(
        version=manifest.version,
        metadata=manifest.metadata,
        sources=manifest.sources,
        images=images,
        containers=containers,
        builds=builds,
        scenarios=scenarios,
    )


def load_values(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    data, locations = _read_yaml(file_path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        line, column = locations.get((), (None, None))
        raise SchemaValidationError(
            "values file must contain a mapping",
            SourceLocation(file_path, line, column),
        )
    return data
