"""Small, deterministic string templates for resolved configuration values."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from ..errors import ResolutionError
from .models import PromptValue

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ROOT_NAMES = frozenset({"WORKSPACE_ROOT", "RIGYARD_ROOT"})
SUPPORTED_DATE_DIRECTIVES = frozenset("aAwdbBmyYHIpMSfzZjUWcxXGuV%")


@dataclass(frozen=True)
class TemplateContext:
    environment: Mapping[str, str]
    local_now: datetime
    utc_now: datetime
    roots: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def capture(
        cls,
        environment: Mapping[str, str],
        *,
        now: datetime | None = None,
        config_path: str | Path | None = None,
        workspace_root: str | Path | None = None,
        variables: Mapping[str, str] | None = None,
    ) -> TemplateContext:
        captured = datetime.now().astimezone() if now is None else now
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ValueError("template time must include timezone information")
        roots: dict[str, str] = {}
        if config_path is not None:
            rigyard_root = Path(config_path).resolve().parent
            roots = {
                "WORKSPACE_ROOT": str(
                    Path.cwd().resolve()
                    if workspace_root is None
                    else Path(workspace_root).resolve()
                ),
                "RIGYARD_ROOT": str(rigyard_root),
            }
        base = cls(
            MappingProxyType(dict(environment)),
            captured,
            captured.astimezone(timezone.utc),
            MappingProxyType(roots),
        )
        if not variables:
            return base
        configured = dict(roots)
        for name, value in variables.items():
            current = cls(
                base.environment,
                base.local_now,
                base.utc_now,
                MappingProxyType(dict(configured)),
            )
            configured[name] = StringTemplateRenderer(current).render(value, f"variables.{name}")
        return cls(
            base.environment,
            base.local_now,
            base.utc_now,
            MappingProxyType(configured),
        )


class StringTemplateRenderer:
    """Render supported expressions once without evaluating replacement text again."""

    def __init__(
        self,
        context: TemplateContext,
        *,
        variable_names: Collection[str] = (),
    ) -> None:
        self.context = context
        self.variable_names = frozenset(variable_names)

    def render(self, value: str, path: str) -> str:
        parts: list[str] = []
        cursor = 0
        while cursor < len(value):
            escaped = value.find("$${", cursor)
            expression = value.find("${", cursor)
            positions = [position for position in (escaped, expression) if position >= 0]
            if not positions:
                parts.append(value[cursor:])
                break
            start = min(positions)
            parts.append(value[cursor:start])
            if start == escaped:
                end = value.find("}", start + 3)
                if end < 0:
                    raise self._error(path, "unterminated escaped template")
                parts.append(value[start + 1 : end + 1])
                cursor = end + 1
                continue
            end = value.find("}", start + 2)
            if end < 0:
                raise self._error(path, "unterminated template")
            source = value[start + 2 : end]
            parts.append(self._evaluate(source, path))
            cursor = end + 1
        rendered = "".join(parts)
        if "\x00" in rendered:
            raise self._error(path, "NUL bytes are not allowed in template results")
        return rendered

    def render_value(self, value: Any, path: str) -> Any:
        if isinstance(value, str):
            return self.render(value, path)
        if isinstance(value, Path):
            return Path(self.render(str(value), path))
        if isinstance(value, Mapping):
            return {
                key: self.render_value(item, f"{path}.{key}" if path else str(key))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                self.render_value(item, f"{path}.{index}" if path else str(index))
                for index, item in enumerate(value)
            ]
        return value

    def validate(self, value: str, path: str) -> None:
        cursor = 0
        while cursor < len(value):
            escaped = value.find("$${", cursor)
            expression = value.find("${", cursor)
            positions = [position for position in (escaped, expression) if position >= 0]
            if not positions:
                return
            start = min(positions)
            if start == escaped:
                end = value.find("}", start + 3)
                if end < 0:
                    raise self._error(path, "unterminated escaped template")
                cursor = end + 1
                continue
            end = value.find("}", start + 2)
            if end < 0:
                raise self._error(path, "unterminated template")
            self._validate_expression(value[start + 2 : end], path)
            cursor = end + 1

    def _evaluate(self, source: str, path: str) -> str:
        kind, argument = self._validate_expression(source, path)
        if kind == "root":
            if argument not in self.context.roots:
                raise self._error(path, f"workspace template {argument!r} requires a config path")
            return self.context.roots[argument]
        if kind == "env":
            if argument not in self.context.environment:
                raise self._error(path, f"missing environment variable {argument!r}")
            return self.context.environment[argument]
        instant = self.context.local_now if kind == "date" else self.context.utc_now
        return instant.strftime(argument)

    def _validate_expression(self, source: str, path: str) -> tuple[str, str]:
        if source in ROOT_NAMES or source in self.context.roots or source in self.variable_names:
            return "root", source
        if ":" not in source:
            raise self._error(path, f"invalid template {source!r}; expected KIND:ARGUMENT")
        kind, argument = source.split(":", 1)
        if kind not in {"env", "date", "utcdate"}:
            raise self._error(path, f"unsupported template kind {kind!r}")
        if not argument:
            raise self._error(path, f"{kind} template argument must not be empty")
        if "${" in argument:
            raise self._error(path, "nested templates are not supported")
        if kind == "env":
            if not ENVIRONMENT_NAME.fullmatch(argument):
                raise self._error(path, f"invalid environment variable name {argument!r}")
        else:
            self._validate_date_format(argument, path)
        return kind, argument

    def _validate_date_format(self, value: str, path: str) -> None:
        cursor = 0
        while cursor < len(value):
            marker = value.find("%", cursor)
            if marker < 0:
                return
            if marker + 1 == len(value):
                raise self._error(path, "date format ends with an incomplete '%' directive")
            directive = value[marker + 1]
            if directive not in SUPPORTED_DATE_DIRECTIVES:
                raise self._error(path, f"unsupported date directive %{directive}")
            cursor = marker + 2

    @staticmethod
    def _error(path: str, message: str) -> ResolutionError:
        prefix = f"{path}: " if path else ""
        return ResolutionError(f"{prefix}{message}")


def validate_template_syntax(
    node: Any,
    prefix: str = "",
    renderer: StringTemplateRenderer | None = None,
    *,
    variable_names: Collection[str] = (),
) -> None:
    """Validate expressions everywhere without reading environment variables."""

    active = renderer or StringTemplateRenderer(
        TemplateContext.capture({}, now=datetime(2000, 1, 1, tzinfo=timezone.utc)),
        variable_names=variable_names,
    )
    if isinstance(node, PromptValue):
        if node.has_default:
            _validate_value(node.default, prefix, active)
        if node.prompt.options is not None:
            _validate_value(node.prompt.options, f"{prefix}.prompt.options", active)
        return
    if isinstance(node, BaseModel):
        for name in type(node).model_fields:
            child = f"{prefix}.{name}" if prefix else name
            validate_template_syntax(getattr(node, name), child, active)
        return
    if isinstance(node, Mapping):
        for name, value in node.items():
            child = f"{prefix}.{name}" if prefix else str(name)
            validate_template_syntax(value, child, active)
        return
    if isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            child = f"{prefix}.{index}" if prefix else str(index)
            validate_template_syntax(value, child, active)
        return
    _validate_value(node, prefix, active)


def _validate_value(value: Any, path: str, renderer: StringTemplateRenderer) -> None:
    if isinstance(value, (str, Path)):
        renderer.validate(str(value), path)
    elif isinstance(value, Mapping):
        for name, item in value.items():
            child = f"{path}.{name}" if path else str(name)
            _validate_value(item, child, renderer)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            child = f"{path}.{index}" if path else str(index)
            _validate_value(item, child, renderer)
