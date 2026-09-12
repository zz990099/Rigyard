"""Strict, predictable conversion and validation of external values."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import ResolutionError
from .models import ParameterSpec, ParameterType

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    raise ValueError("expected one of true/false, yes/no, on/off, or 1/0")


def _as_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, tuple):
        return list(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("JSON input must be a list")
            return parsed
        if not stripped:
            return []
        return [item.strip() for item in stripped.split(",")]
    raise ValueError("expected a YAML/JSON list or a comma-separated string")


def _convert(raw: Any, kind: ParameterType) -> Any:
    if kind == ParameterType.STRING:
        if isinstance(raw, (dict, list, tuple)):
            raise ValueError("expected a scalar string")
        return str(raw)
    if kind == ParameterType.INT:
        if isinstance(raw, bool):
            raise ValueError("boolean is not an integer")
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError("expected a whole number")
        return int(raw)
    if kind == ParameterType.FLOAT:
        if isinstance(raw, bool):
            raise ValueError("boolean is not a float")
        return float(raw)
    if kind == ParameterType.BOOL:
        return _as_bool(raw)
    if kind == ParameterType.PATH:
        if not isinstance(raw, (str, Path)):
            raise ValueError("expected a path string")
        return Path(raw).expanduser()
    if kind == ParameterType.LIST:
        return _as_list(raw)
    return raw


def coerce_value(name: str, raw: Any, spec: ParameterSpec) -> Any:
    try:
        value = raw if spec.type == ParameterType.CHOICE else _convert(raw, spec.type)

        if spec.type == ParameterType.LIST and spec.item_type is not None:
            value = [_convert(item, spec.item_type) for item in value]

        if spec.type == ParameterType.CHOICE and value not in (spec.options or ()):
            choices = ", ".join(repr(item) for item in spec.options or ())
            raise ValueError(f"expected one of: {choices}")

        if spec.type in {ParameterType.INT, ParameterType.FLOAT}:
            if spec.min is not None and value < spec.min:
                raise ValueError(f"must be greater than or equal to {spec.min}")
            if spec.max is not None and value > spec.max:
                raise ValueError(f"must be less than or equal to {spec.max}")

        if spec.type == ParameterType.LIST:
            if spec.min is not None and len(value) < spec.min:
                raise ValueError(f"must contain at least {int(spec.min)} item(s)")
            if spec.max is not None and len(value) > spec.max:
                raise ValueError(f"must contain at most {int(spec.max)} item(s)")

        if (
            spec.type == ParameterType.STRING
            and spec.pattern is not None
            and re.fullmatch(spec.pattern, value) is None
        ):
            raise ValueError(f"must match regular expression {spec.pattern!r}")

        if spec.type == ParameterType.PATH and spec.must_exist and not value.exists():
            raise ValueError(f"path does not exist: {value}")
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"invalid value for parameter {name!r}: {exc}") from exc
