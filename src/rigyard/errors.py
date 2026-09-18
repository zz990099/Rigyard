"""Actionable errors exposed by rigyard application boundaries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceLocation:
    path: Path
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        if self.line is None:
            return str(self.path)
        if self.column is None:
            return f"{self.path}:{self.line}"
        return f"{self.path}:{self.line}:{self.column}"


class RigyardError(Exception):
    """Base class for errors suitable for CLI display."""

    exit_code = 1

    def __init__(self, message: str, location: SourceLocation | None = None) -> None:
        self.message = message
        self.location = location
        super().__init__(self.render())

    def render(self) -> str:
        prefix = f"{self.location}: " if self.location else ""
        return f"{prefix}{self.message}"


class ConfigIOError(RigyardError):
    """The configuration could not be read or parsed as YAML."""

    exit_code = 2


class SchemaValidationError(RigyardError):
    """A YAML document does not conform to the active schema."""

    exit_code = 2


class WorkspaceError(RigyardError):
    """A workspace binding cannot be read or updated."""

    exit_code = 2


class ResolutionError(RigyardError):
    """A runtime value could not be resolved or validated."""

    exit_code = 3


class MissingValueError(ResolutionError):
    def __init__(self, names: Iterable[str]) -> None:
        ordered = sorted(names)
        joined = ", ".join(ordered)
        super().__init__(
            f"missing required runtime value(s): {joined}; provide a values file, "
            "environment variables, "
            "--set overrides, or run interactively"
        )
        self.names = tuple(ordered)


class BuildPlanError(RigyardError):
    """A project build definition cannot be converted into an execution plan."""

    exit_code = 3


class BuildExecutionError(RigyardError):
    """A configured project build process failed."""

    exit_code = 4


class ScenarioPlanError(RigyardError):
    """A scenario cannot be converted into a backend execution plan."""

    exit_code = 3


class ScenarioExecutionError(RigyardError):
    """A scenario backend operation failed."""

    exit_code = 4


class ImageConfigError(RigyardError):
    """An image definition or Dockerfile fragment is invalid."""

    exit_code = 2


class ImagePlanError(RigyardError):
    """An image definition cannot be materialized into a build plan."""

    exit_code = 3


class BackendUnavailableError(RigyardError):
    """The requested execution backend is not available."""

    exit_code = 4


class ImageBuildError(RigyardError):
    """A backend failed while building an image layer."""

    exit_code = 4


class ContainerPlanError(RigyardError):
    """A container definition cannot be resolved into an execution plan."""

    exit_code = 3


class ContainerCreateError(RigyardError):
    """Docker failed to create and start a container."""

    exit_code = 4


class ContainerLifecycleError(ContainerCreateError):
    """A lifecycle hook failed after its container was created."""
