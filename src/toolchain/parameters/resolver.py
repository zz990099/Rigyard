"""Discover and resolve inline prompt values for one selected operation."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import MissingValueError, ResolutionError, ToolchainError
from .context import ResolvedContext, ResolvedValue, ValueSource
from .models import PromptMode, PromptValue
from .prompt import InputFunction, prompt_for_value
from .templates import StringTemplateRenderer, TemplateContext

ENV_PREFIX = "TOOL_PARAM_"
ModelT = TypeVar("ModelT", bound=BaseModel)
DefaultRenderer = Callable[[str, Any], str]


def environment_name(path: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "_", path).upper()
    return f"{ENV_PREFIX}{suffix}"


def collect_prompts(node: Any, prefix: str = "") -> dict[str, PromptValue]:
    result: dict[str, PromptValue] = {}
    if isinstance(node, PromptValue):
        result[prefix] = node
    elif isinstance(node, BaseModel):
        for name in type(node).model_fields:
            child = f"{prefix}.{name}" if prefix else name
            result.update(collect_prompts(getattr(node, name), child))
    elif isinstance(node, Mapping):
        for name, value in node.items():
            child = f"{prefix}.{name}" if prefix else str(name)
            result.update(collect_prompts(value, child))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            child = f"{prefix}.{index}" if prefix else str(index)
            result.update(collect_prompts(value, child))
    return result


def flatten_values(values: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(values, Mapping):
        for name, value in values.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            result.update(flatten_values(value, path))
    elif (
        isinstance(values, (list, tuple))
        and values
        and all(isinstance(value, Mapping) for value in values)
    ):
        for index, value in enumerate(values):
            path = f"{prefix}.{index}" if prefix else str(index)
            result.update(flatten_values(value, path))
    elif prefix:
        result[prefix] = values
    return result


class RuntimeValueResolver:
    def __init__(
        self,
        prompts: Mapping[str, PromptValue],
        *,
        render_default: DefaultRenderer | None = None,
    ) -> None:
        self.prompts = dict(prompts)
        self.render_default = render_default
        self._check_environment_collisions()

    def _default_display(self, path: str, value: PromptValue) -> str | None:
        """Render one prompt default for display; a broken template falls back to raw."""
        if not value.has_default:
            return None
        if self.render_default is None:
            return str(value.default)
        try:
            return self.render_default(path, value.default)
        except ToolchainError:
            return str(value.default)

    def _check_environment_collisions(self) -> None:
        names: dict[str, str] = {}
        for path in self.prompts:
            env_name = environment_name(path)
            if env_name in names:
                raise ResolutionError(
                    f"runtime values {names[env_name]!r} and {path!r} map to {env_name}"
                )
            names[env_name] = path

    def inspect(self) -> dict[str, Any]:
        return {
            path: {
                "mode": value.prompt.mode.value,
                "message": value.prompt.message,
                "repeat": value.prompt.repeat,
                "options": list(value.prompt.options) if value.prompt.options else None,
                "has_default": value.has_default,
                "environment": environment_name(path),
            }
            for path, value in self.prompts.items()
        }

    def resolve(
        self,
        values: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        overrides: Mapping[str, Any] | None = None,
        *,
        interactive: bool = True,
        input_fn: InputFunction = input,
        allow_missing: bool = False,
    ) -> ResolvedContext:
        flat_values = flatten_values(values or {})
        environment = os.environ if environ is None else environ
        overrides = overrides or {}
        self._reject_unknown("values", flat_values)
        self._reject_unknown("override", overrides)
        resolved: dict[str, ResolvedValue] = {}
        missing: list[str] = []

        for path, prompt in self.prompts.items():
            candidate: tuple[Any, ValueSource] | None = None
            if path in flat_values:
                candidate = (flat_values[path], ValueSource.VALUES)
            env_name = environment_name(path)
            if env_name in environment:
                candidate = (environment[env_name], ValueSource.ENVIRONMENT)
            if path in overrides:
                candidate = (overrides[path], ValueSource.CLI)
            if candidate is not None:
                raw, source = candidate
                resolved[path] = ResolvedValue(self._normalize(path, prompt, raw), source)
            elif interactive:
                resolved[path] = ResolvedValue(
                    prompt_for_value(
                        prompt,
                        input_fn,
                        default_display=self._default_display(path, prompt),
                    ),
                    ValueSource.INTERACTIVE,
                )
            elif prompt.has_default:
                resolved[path] = ResolvedValue(prompt.default, ValueSource.DEFAULT)
            else:
                missing.append(path)

        if missing and not allow_missing:
            raise MissingValueError(missing)
        return ResolvedContext(resolved)

    def _normalize(self, path: str, value: PromptValue, raw: Any) -> Any:
        prompt = value.prompt
        if prompt.mode == PromptMode.CONFIRM:
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                normalized = raw.strip().lower()
                if normalized in {"y", "yes", "true", "1", "on"}:
                    return True
                if normalized in {"n", "no", "false", "0", "off"}:
                    return False
            raise ResolutionError(f"invalid confirm value for {path}: {raw!r}")
        if prompt.mode == PromptMode.SELECT:
            options = prompt.options or ()
            if raw in options:
                return raw
            matches = [option for option in options if str(option) == str(raw)]
            if len(matches) == 1:
                return matches[0]
            raise ResolutionError(
                f"invalid select value for {path}: {raw!r}; expected one of {list(options)!r}"
            )
        if prompt.repeat:
            if not isinstance(raw, (list, tuple)):
                raise ResolutionError(f"invalid repeated input for {path}: expected a list")
            return list(raw)
        return raw

    def _reject_unknown(self, source: str, values: Mapping[str, Any]) -> None:
        unknown = set(values) - set(self.prompts)
        if unknown:
            raise ResolutionError(
                f"unknown runtime value(s) in {source}: {', '.join(sorted(unknown))}"
            )


def materialize(
    node: Any,
    prefix: str,
    context: ResolvedContext,
    renderer: StringTemplateRenderer | None = None,
) -> Any:
    renderer = renderer or StringTemplateRenderer(TemplateContext.capture(os.environ))
    if isinstance(node, PromptValue):
        if prefix not in context:
            raise MissingValueError((prefix,))
        return renderer.render_value(context[prefix], prefix)
    if isinstance(node, BaseModel):
        return {
            name: materialize(
                getattr(node, name),
                f"{prefix}.{name}" if prefix else name,
                context,
                renderer,
            )
            for name in type(node).model_fields
        }
    if isinstance(node, Mapping):
        return {
            name: materialize(
                value,
                f"{prefix}.{name}" if prefix else str(name),
                context,
                renderer,
            )
            for name, value in node.items()
        }
    if isinstance(node, (list, tuple)):
        return [
            materialize(
                value,
                f"{prefix}.{index}" if prefix else str(index),
                context,
                renderer,
            )
            for index, value in enumerate(node)
        ]
    if isinstance(node, str):
        return renderer.render(node, prefix)
    if isinstance(node, Path):
        return Path(renderer.render(str(node), prefix))
    return node


def materialize_as(
    template: BaseModel,
    prefix: str,
    context: ResolvedContext,
    target: type[ModelT],
    renderer: StringTemplateRenderer | None = None,
) -> ModelT:
    try:
        return target.model_validate(materialize(template, prefix, context, renderer))
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first.get("loc", ()))
        path = f"{prefix}.{location}" if location else prefix
        raise ResolutionError(f"invalid resolved value for {path}: {first['msg']}") from exc
