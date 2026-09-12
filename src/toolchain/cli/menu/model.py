"""Code-owned action descriptors for the interactive menu."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import MenuSession


@dataclass(frozen=True)
class MenuAction:
    key: str
    label: str
    handler: Callable[[MenuSession], None]
    enabled: Callable[[MenuSession], bool] = lambda _: True
    disabled_reason: str = "unavailable"


@dataclass(frozen=True)
class MenuRegistry:
    actions: tuple[MenuAction, ...]
