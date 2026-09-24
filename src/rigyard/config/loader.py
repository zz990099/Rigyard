"""Load a v3 project manifest and its referenced YAML configuration sources."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, RootModel, ValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ..errors import ConfigIOError, SchemaValidationError, SourceLocation
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .models import (
    BuildDefinitions,
    ContainerDefinitions,
    ImageDefinitions,
    RigyardBranding,
    RigyardConfig,
    RigyardManifest,
    ScenarioDefinitions,
    SourceFileInfo,
    TaskDefinitions,
    TestDefinitions,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
RootModelT = TypeVar("RootModelT", bound=RootModel[Any])


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Reject ambiguous mappings while retaining PyYAML's safe constructors."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._checked_mappings: set[MappingNode] = set()

    def flatten_mapping(self, node: MappingNode) -> None:
        # Validate each original mapping before merge expansion mutates its keys.
        # SafeLoader recursively calls this method for inline and aliased merge sources.
        if node not in self._checked_mappings:
            self._check_keys(node)
            self._checked_mappings.add(node)
        super().flatten_mapping(node)

    def _check_keys(self, node: MappingNode) -> None:
        seen: dict[Any, tuple[int, int]] = {}
        for key_node, _ in node.value:
            # A merge key is handled by SafeLoader; only explicit scalar keys are checked.
            if not isinstance(key_node, ScalarNode) or key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node)
            if key in seen:
                line, column = seen[key]
                raise ConstructorError(
                    None,
                    None,
                    f"duplicate key {key!r} (first defined at line {line}, column {column})",
                    key_node.start_mark,
                )
            seen[key] = (key_node.start_mark.line + 1, key_node.start_mark.column + 1)


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
        data = yaml.load(text, Loader=UniqueKeySafeLoader)
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = SourceLocation(
            file_path,
            mark.line + 1 if mark else None,
            mark.column + 1 if mark else None,
        )
        problem = getattr(exc, "problem", exc)
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


def _source_paths(manifest_path: Path, configured: Path | tuple[Path, ...]) -> tuple[Path, ...]:
    if isinstance(configured, tuple):
        return tuple(_source_path(manifest_path, item) for item in configured)
    return (_source_path(manifest_path, configured),)


def _load_branding(manifest_path: Path, manifest: RigyardManifest) -> RigyardBranding:
    configured = manifest.branding
    if configured.logo_file is None:
        return RigyardBranding(logo=configured.logo)

    renderer = StringTemplateRenderer(
        TemplateContext.capture(
            os.environ,
            config_path=manifest_path,
            variables=manifest.variables,
        )
    )
    rendered = renderer.render(str(configured.logo_file), "branding.logo_file")
    logo_path = Path(rendered).expanduser()
    if not logo_path.is_absolute():
        logo_path = manifest_path.parent / logo_path
    logo_path = logo_path.resolve()
    try:
        logo = logo_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigIOError(str(exc), SourceLocation(logo_path)) from exc
    return _validate_data(
        logo_path,
        {"logo": logo},
        {},
        RigyardBranding,
        label="branding logo",
    )


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
    model: type[RootModelT],
    *,
    label: str,
) -> tuple[SourceFileInfo, ...]:
    files: list[SourceFileInfo] = []
    for source in _source_paths(manifest_path, configured):
        data, locations = _read_yaml(source)
        if data is None:
            raise SchemaValidationError(f"{label} must not be empty", SourceLocation(source))
        description = _source_description(source, data, locations)
        if isinstance(data, Mapping) and "description" in data:
            data = {key: value for key, value in data.items() if key != "description"}
        validated = _validate_data(source, data, locations, model, label=label)
        files.append(
            SourceFileInfo(
                path=source,
                description=description,
                names=tuple(validated.root),
                definitions=dict(validated.root),
            )
        )
    return tuple(files)


def _load_optional_source_group(
    manifest_path: Path,
    configured: Path | tuple[Path, ...] | None,
    model: type[RootModelT],
    *,
    label: str,
) -> tuple[SourceFileInfo, ...]:
    if configured is None:
        return ()
    return _load_source_group(manifest_path, configured, model, label=label)


def load_config(path: str | Path) -> RigyardConfig:
    manifest_path = Path(path).resolve()
    manifest = _validate_file(manifest_path, RigyardManifest, label="manifest")
    branding = _load_branding(manifest_path, manifest)
    image_files = _load_optional_source_group(
        manifest_path, manifest.sources.images, ImageDefinitions, label="image source"
    )
    container_files = _load_optional_source_group(
        manifest_path,
        manifest.sources.containers,
        ContainerDefinitions,
        label="container source",
    )
    build_files = _load_optional_source_group(
        manifest_path, manifest.sources.builds, BuildDefinitions, label="build source"
    )
    test_files = _load_optional_source_group(
        manifest_path, manifest.sources.tests, TestDefinitions, label="test source"
    )
    task_files = _load_optional_source_group(
        manifest_path, manifest.sources.tasks, TaskDefinitions, label="task source"
    )
    scenario_files = _load_optional_source_group(
        manifest_path, manifest.sources.scenarios, ScenarioDefinitions, label="scenario source"
    )
    return RigyardConfig(
        version=manifest.version,
        metadata=manifest.metadata,
        workspace=manifest.workspace,
        branding=branding,
        sources=manifest.sources,
        variables=manifest.variables,
        source_files={
            "images": image_files,
            "containers": container_files,
            "builds": build_files,
            "tests": test_files,
            "tasks": task_files,
            "scenarios": scenario_files,
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
