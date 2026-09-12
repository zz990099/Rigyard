"""Minimal interactive prompt adapter, isolated for alternative frontends."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .coercion import coerce_value
from .models import ParameterSpec, ParameterType

InputFunction = Callable[[str], str]


def prompt_for_value(name: str, spec: ParameterSpec, input_fn: InputFunction = input) -> Any:
    description = f" ({spec.description})" if spec.description else ""
    choice_hint = ""
    if spec.type == ParameterType.CHOICE:
        choice_hint = f" [{'/'.join(str(item) for item in spec.options or ())}]"
    while True:
        raw = input_fn(f"{name}{description}{choice_hint}: ")
        try:
            return coerce_value(name, raw, spec)
        except Exception as exc:  # retry is the intended interactive boundary
            print(f"Error: {exc}")
