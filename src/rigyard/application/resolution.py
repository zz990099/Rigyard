"""Typed shared preparation for one source-qualified resource specification."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from ..config.catalog import DefinitionCatalog
from ..errors import SchemaValidationError
from ..parameters.prompt import Formatter
from ..parameters.sources import DynamicSources
from ..parameters.templates import StringTemplateRenderer, TemplateContext
from .parameters import resolve_template
from .project import ProjectContext
from .requests import ResolutionRequest

SpecT = TypeVar("SpecT", bound=BaseModel)


def resolve_definition(
    project: ProjectContext,
    request: ResolutionRequest,
    kind: str,
    name: str,
    target: type[SpecT],
    *,
    sources: DynamicSources,
    formatter: Formatter | None,
) -> SpecT:
    catalog = DefinitionCatalog(project.config, project.config_path)
    match = catalog.find(kind, name, request.source_path)
    if match is None:
        available = ", ".join(sorted({e.name for e in catalog.entries if e.kind == kind})) or "none"
        raise SchemaValidationError(f"unknown {kind[:-1]} {name!r}; configured {kind}: {available}")
    renderer = StringTemplateRenderer(
        TemplateContext.capture(
            project.environment,
            now=project.timestamp,
            config_path=project.config_path,
            workspace_root=project.workspace_root,
            variables=project.config.variables,
        ).with_source(match.source_path)
    )
    spec, _ = resolve_template(
        project.config,
        match.value,
        request,
        match.prefix,
        target,
        renderer,
        sources,
        formatter,
        environment=project.environment,
    )
    return spec
