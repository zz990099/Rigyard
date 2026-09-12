"""Immutable output of parameter resolution."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


class ValueSource(str, Enum):
    DEFAULT = "default"
    VALUES = "values"
    ENVIRONMENT = "environment"
    CLI = "cli"
    INTERACTIVE = "interactive"


@dataclass(frozen=True)
class ResolvedValue:
    value: Any
    source: ValueSource


class ResolvedContext(Mapping[str, Any]):
    """Read-only mapping with source metadata and disabled-parameter tracking."""

    def __init__(
        self,
        values: Mapping[str, ResolvedValue],
        disabled: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self._resolved = MappingProxyType(dict(values))
        self._disabled = frozenset(disabled)

    def __getitem__(self, key: str) -> Any:
        return self._resolved[key].value

    def __iter__(self) -> Iterator[str]:
        return iter(self._resolved)

    def __len__(self) -> int:
        return len(self._resolved)

    @property
    def disabled(self) -> frozenset[str]:
        return self._disabled

    def resolved(self, key: str) -> ResolvedValue:
        return self._resolved[key]

    def as_dict(self, include_sources: bool = False) -> dict[str, Any]:
        if include_sources:
            return {
                name: {"value": item.value, "source": item.source.value}
                for name, item in self._resolved.items()
            }
        return {name: item.value for name, item in self._resolved.items()}
