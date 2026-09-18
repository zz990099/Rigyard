"""Load a v2 project manifest and its referenced YAML configuration sources."""

from __future__ import annotations

from collections.abc import Mapping
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
    SourceFileInfo,
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


def _validate_data(
    path: Path,
    data: Any,
    locations: dict[tuple[Any, ...], tuple[int, int]],
    model: type[ModelT],
    *,
    label: str,
) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        error_path = tuple(first.get("loc", ()))
        location = _nearest_location(path, locations, error_path)
        dotted = ".".join(str(part) for part in error_path)
        prefix = f"{dotted}: " if dotted else ""
        raise SchemaValidationError(f"{prefix}{first['msg']}", location) from exc


def _validate_file(path: Path, model: type[ModelT], *, label: str) -> ModelT:
    data, locations = _read_yaml(path)
    if data is None:
        raise SchemaValidationError(f"{label} must not be empty", SourceLocation(path))
    return _validate_data(path, data, locations, model, label=label)


def _source_path(manifest_path: Path, configured: Path) -> Path:
    source = configured.expanduser()
    if not source.is_absolute():
        source = manifest_path.parent / source
    return source.resolve()


def _source_paths(
    manifest_path: Path, configured: Path | tuple[Path, ...]
) -> tuple[Path, ...]:
    if isinstance(configured, tuple):
        return tuple(_source_path(manifest_path, item) for item in configured)
    return (_source_path(manifest_path, configured),)


def _source_description(
    path: Path,
    data: Any,
    locations: dict[tuple[Any, ...], tuple[int, int]],
) -> str | None:
    if not isinstance(data, Mapping) or "description" not in data:
        return None
    value = data["description"]
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(
            "source description must be a non-empty string",
            _nearest_location(path, locations, ("description",)),
        )
    return value


def _load_source_group(
    manifest_path: Path,
    configured: Path | tuple[Path, ...],
    model: type[ModelT],
    *,
    label: str,
) -> tuple[
    dict[str, Any],
    tuple[SourceFileInfo, ...],
    dict[str, tuple[Path, ...]],
]:
    definitions: dict[str, Any] = {}
    origins: dict[str, Path] = {}
    duplicates: dict[str, tuple[Path, ...]] = {}
    files: list[SourceFileInfo] = []
    for source in _source_paths(manifest_path, configured):
        data, locations = _read_yaml(source)
        if data is None:
            raise SchemaValidationError(f"{label} must not be empty", SourceLocation(source))
        description = _source_description(source, data, locations)
        if isinstance(data, Mapping) and "description" in data:
            data = {key: value for key, value in data.items() if key != "description"}
        validated = _validate_data(source, data, locations, model, label=label)
        for name in validated.root:
            if name in origins:
                paths = list(duplicates.get(name, (origins[name],)))
                if source not in paths:
                    paths.append(source)
                duplicates[name] = tuple(paths)
                continue
            origins[name] = source
            definitions[name] = validated.root[name]
        files.append(
            SourceFileInfo(
                path=source,
                description=description,
                names=tuple(validated.root),
                definitions=dict(validated.root),
            )
        )
    return definitions, tuple(files), duplicates


def _load_optional_source_group(
    manifest_path: Path,
    configured: Path | tuple[Path, ...] | None,
    model: type[ModelT],
    *,
    label: str,
) -> tuple[
    dict[str, Any],
    tuple[SourceFileInfo, ...],
    dict[str, tuple[Path, ...]],
]:
    if configured is None:
        return {}, (), {}
    return _load_source_group(manifest_path, configured, model, label=label)


def load_config(path: str | Path) -> ToolchainConfig:
    manifest_path = Path(path).resolve()
    manifest = _validate_file(manifest_path, ToolchainManifest, label="manifest")
    images, image_files, image_duplicates = _load_optional_source_group(
        manifest_path, manifest.sources.images, ImageDefinitions, label="image source"
    )
    containers, container_files, container_duplicates = _load_optional_source_group(
        manifest_path,
        manifest.sources.containers,
        ContainerDefinitions,
        label="container source",
    )
    builds, build_files, build_duplicates = _load_optional_source_group(
        manifest_path, manifest.sources.builds, BuildDefinitions, label="build source"
    )
    scenarios, scenario_files, scenario_duplicates = _load_optional_source_group(
        manifest_path, manifest.sources.scenarios, ScenarioDefinitions, label="scenario source"
    )
    return ToolchainConfig(
        version=manifest.version,
        metadata=manifest.metadata,
        sources=manifest.sources,
        variables=manifest.variables,
        images=images,
        containers=containers,
        builds=builds,
        scenarios=scenarios,
        source_files={
            "images": image_files,
            "containers": container_files,
            "builds": build_files,
            "scenarios": scenario_files,
        },
        duplicate_names={
            "images": image_duplicates,
            "containers": container_duplicates,
            "builds": build_duplicates,
            "scenarios": scenario_duplicates,
        },
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
