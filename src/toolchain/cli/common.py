"""Shared CLI parsing and rendering helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def parse_overrides(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"invalid --set {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if not name:
            raise argparse.ArgumentTypeError("--set parameter name must not be empty")
        result[name] = value
    return result


def serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def emit(data: Any, output_format: str) -> None:
    normalized = serializable(data)
    if output_format == "json":
        print(json.dumps(normalized, indent=2, ensure_ascii=False))
    else:
        print(yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True).rstrip())

