"""Semantic ANSI styling shared by the terminal frontends.

Roles describe what a piece of text *means* (title, label, value, error, …), so the
palette lives in one place. Styling is only applied when the target stream is a
terminal unless it is forced, which keeps CI logs, pipes and test assertions free of
escape sequences.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import TextIO

RESET = "\x1b[0m"


class ColorMode(str, Enum):
    """How to decide whether a stream gets escape sequences."""

    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


@dataclass(frozen=True)
class Line:
    """One output line split into ``(role, text)`` parts.

    ``text()`` and ``str(line)`` return the plain rendering, so callers that only
    need the text (logs, tests) keep working without knowing about the roles.
    """

    parts: tuple[tuple[str | None, str], ...]

    def text(self) -> str:
        return "".join(part for _, part in self.parts)

    def render(self, style: "Style") -> str:
        return "".join(
            style.render(role, part) if role else part for role, part in self.parts
        )

    def __str__(self) -> str:
        return self.text()


def line(*parts: "tuple[str | None, str] | str") -> Line:
    """Build a line from ``(role, text)`` pairs or plain text parts."""

    return Line(tuple((None, part) if isinstance(part, str) else part for part in parts))


def field(name: str, value: str) -> Line:
    """Build a ``Key: value`` line with a dim name and a bold value."""

    return line(("label", name), ": ", ("value", value))


@dataclass(frozen=True)
class Theme:
    """Role to SGR parameter mapping, e.g. ``{"title": "1;36"}``."""

    roles: Mapping[str, str] = dataclass_field(default_factory=dict)

    def codes(self, role: str) -> str | None:
        return self.roles.get(role)


DEFAULT_THEME = Theme(
    {
        "title": "1;36",
        "heading": "1",
        "label": "2",
        "value": "1",
        "number": "36",
        "muted": "2",
        "success": "32",
        "warning": "33",
        "error": "1;31",
    }
)


@dataclass(frozen=True)
class Style:
    """Render text for one role; a disabled style returns its input unchanged."""

    theme: Theme = DEFAULT_THEME
    enabled: bool = False

    @classmethod
    def plain(cls) -> Style:
        return cls()

    @classmethod
    def for_stream(
        cls,
        stream: TextIO,
        *,
        mode: ColorMode | str = ColorMode.AUTO,
        environ: Mapping[str, str] | None = None,
    ) -> Style:
        environment = os.environ if environ is None else environ
        color_mode = ColorMode(mode)
        if color_mode is ColorMode.ALWAYS:
            return cls(enabled=True)
        if color_mode is ColorMode.NEVER:
            return cls()
        if environment.get("NO_COLOR") or environment.get("TERM") == "dumb":
            return cls()
        isatty = getattr(stream, "isatty", None)
        return cls(enabled=bool(isatty is not None and isatty()))

    def render(self, role: str, text: str) -> str:
        if not self.enabled or not text:
            return text
        codes = self.theme.codes(role)
        return f"\x1b[{codes}m{text}{RESET}" if codes else text

    def line(self, text: str) -> str:
        """Style a ``Key: value`` line; lines without that shape stay as they are."""

        label, separator, value = text.partition(": ")
        if not separator:
            return text
        return f"{self.render('label', label)}: {self.render('value', value)}"
