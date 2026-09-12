"""Resolve explicit scalar parameter references used by image definitions."""

from __future__ import annotations

from typing import Any

from ..errors import ImagePlanError
from ..parameters.context import ResolvedContext
from .models import ParameterRef, ScalarSource


def resolve_scalar(
    source: ScalarSource,
    context: ResolvedContext,
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    value: Any
    if isinstance(source, ParameterRef):
        if source.parameter not in context:
            raise ImagePlanError(
                f"{field} references unresolved or disabled parameter {source.parameter!r}"
            )
        value = context[source.parameter]
    else:
        value = source

    rendered = str(value).lower() if isinstance(value, bool) else str(value)
    if not allow_empty and not rendered:
        raise ImagePlanError(f"{field} must not resolve to an empty value")
    return rendered
