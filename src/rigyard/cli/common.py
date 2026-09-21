"""Shared CLI parsing and rendering helpers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TextIO

import yaml

from .style import Line, Style


def say(
    style: Style,
    message: str,
    role: str = "success",
    *,
    stream: TextIO | None = None,
) -> None:
    """Print one styled status line."""

    print(style.render(role, message), file=stream)


def print_fields(
    style: Style,
    lines: Iterable[Line | str],
    *,
    stream: TextIO | None = None,
) -> None:
    """Print rendered plan lines with dimmed field names."""

    print("\n".join(_render_field(style, item) for item in lines), file=stream)


def _render_field(style: Style, item: Line | str) -> str:
    return item.render(style) if isinstance(item, Line) else style.line(item)


def parse_overrides(items: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"invalid --set {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if not name:
            raise argparse.ArgumentTypeError("--set configuration path must not be empty")
        try:
            result[name] = yaml.safe_load(value)
        except yaml.YAMLError as exc:
            raise argparse.ArgumentTypeError(f"invalid YAML value in --set {item!r}") from exc
    return result


def serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def emit(data: Any, output_format: str, *, stream: TextIO | None = None) -> None:
    normalized = serializable(data)
    if output_format == "json":
        print(json.dumps(normalized, indent=2, ensure_ascii=False), file=stream)
    else:
        print(
            yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True).rstrip(),
            file=stream,
        )


def stream_input(
    input_stream: TextIO, output_stream: TextIO
) -> Callable[[str], str]:
    """Create an ``input``-compatible reader over injected CLI streams."""

    def read(prompt: str) -> str:
        print(prompt, end="", file=output_stream, flush=True)
        value = input_stream.readline()
        if value == "":
            raise EOFError
        return value.rstrip("\r\n")

    return read
