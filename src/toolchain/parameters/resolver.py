"""Parameter resolution pipeline."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from ..errors import MissingValueError, ResolutionError
from .coercion import coerce_value
from .conditions import evaluate_condition
from .context import ResolvedContext, ResolvedValue, ValueSource
from .graph import build_dependencies, topological_order
from .models import ParameterSchema, ParameterSpec
from .prompt import InputFunction, prompt_for_value

ENV_PREFIX = "TOOL_PARAM_"


def environment_name(parameter_name: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "_", parameter_name).upper()
    return f"{ENV_PREFIX}{suffix}"


class ParameterEngine:
    """Resolve a validated schema into one immutable context."""

    def __init__(self, schema: ParameterSchema) -> None:
        self.schema = schema
        self.dependencies = build_dependencies(schema.parameters)
        self.order = topological_order(schema.parameters)
        self._check_environment_collisions()
        self._validate_defaults()

    def _check_environment_collisions(self) -> None:
        names: dict[str, str] = {}
        for parameter in self.schema.parameters:
            env_name = environment_name(parameter)
            if env_name in names:
                raise ResolutionError(
                    f"parameters {names[env_name]!r} and {parameter!r} map to the same "
                    f"environment variable {env_name}"
                )
            names[env_name] = parameter

    def _validate_defaults(self) -> None:
        for name, spec in self.schema.parameters.items():
            if "default" in spec.model_fields_set:
                coerce_value(name, spec.default, spec)

    def inspect(self) -> dict[str, Any]:
        return {
            "version": self.schema.version,
            "order": list(self.order),
            "parameters": {
                name: {
                    "type": spec.type.value,
                    "required": spec.required,
                    "dependencies": sorted(self.dependencies[name]),
                    "environment": environment_name(name),
                    "enabled_if": spec.enabled_if,
                    "required_if": spec.required_if,
                }
                for name, spec in self.schema.parameters.items()
            },
        }

    def resolve(
        self,
        values: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        overrides: Mapping[str, Any] | None = None,
        *,
        interactive: bool = True,
        input_fn: InputFunction = input,
    ) -> ResolvedContext:
        values = values or {}
        environ = os.environ if environ is None else environ
        overrides = overrides or {}
        self._reject_unknown("values", values)
        self._reject_unknown("CLI override", overrides)

        resolved: dict[str, ResolvedValue] = {}
        disabled: set[str] = set()
        missing: list[str] = []

        for name in self.order:
            spec = self.schema.parameters[name]
            current_values = {key: item.value for key, item in resolved.items()}
            if spec.enabled_if is not None and not evaluate_condition(
                spec.enabled_if, current_values
            ):
                disabled.add(name)
                continue

            candidate = self._candidate(name, spec, values, environ, overrides)
            required = spec.required or (
                spec.required_if is not None
                and evaluate_condition(spec.required_if, current_values)
            )
            if candidate is None:
                if required and interactive:
                    value = prompt_for_value(name, spec, input_fn)
                    resolved[name] = ResolvedValue(value, ValueSource.INTERACTIVE)
                elif required:
                    missing.append(name)
                continue

            raw, source = candidate
            resolved[name] = ResolvedValue(coerce_value(name, raw, spec), source)

        if missing:
            raise MissingValueError(missing)
        return ResolvedContext(resolved, disabled)

    def _candidate(
        self,
        name: str,
        spec: ParameterSpec,
        values: Mapping[str, Any],
        environ: Mapping[str, str],
        overrides: Mapping[str, Any],
    ) -> tuple[Any, ValueSource] | None:
        # Later layers intentionally replace earlier layers.
        candidate: tuple[Any, ValueSource] | None = None
        if "default" in spec.model_fields_set:
            candidate = (spec.default, ValueSource.DEFAULT)
        if name in values:
            candidate = (values[name], ValueSource.VALUES)
        env_name = environment_name(name)
        if env_name in environ:
            candidate = (environ[env_name], ValueSource.ENVIRONMENT)
        if name in overrides:
            candidate = (overrides[name], ValueSource.CLI)
        return candidate

    def _reject_unknown(self, source: str, values: Mapping[str, Any]) -> None:
        unknown = set(values) - set(self.schema.parameters)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise ResolutionError(f"unknown parameter(s) in {source}: {joined}")
