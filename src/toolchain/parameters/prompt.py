"""Terminal acquisition for inline prompt values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import PromptMode, PromptValue

InputFunction = Callable[[str], str]


def prompt_for_value(
    value: PromptValue,
    input_fn: InputFunction = input,
    *,
    default_display: str | None = None,
) -> Any:
    """Acquire one prompt value from the terminal.

    ``default_display`` is the default as it should be shown to the user, i.e. already
    expanded through the string templates (``${env:USER}`` → ``root``). When it is
    omitted the raw default is displayed; prompts without a default show no hint.
    The value returned for an accepted default stays the raw one: it is rendered once
    more together with the rest of the selected definition.
    """
    prompt = value.prompt
    if default_display is None and value.has_default:
        default_display = str(value.default)
    default_hint = f" [{default_display}]" if default_display is not None else ""
    if prompt.mode == PromptMode.CONFIRM:
        default_hint = "Y/n" if value.has_default and value.default else "y/N"
        while True:
            raw = input_fn(f"{prompt.message} [{default_hint}]: ").strip().lower()
            if not raw and value.has_default:
                return value.default
            if raw in {"y", "yes", "true", "1", "on"}:
                return True
            if raw in {"n", "no", "false", "0", "off"}:
                return False

    if prompt.mode == PromptMode.SELECT:
        options = prompt.options or ()
        choices = ", ".join(f"{index}={item}" for index, item in enumerate(options, 1))
        while True:
            raw = input_fn(f"{prompt.message} ({choices}){default_hint}: ").strip()
            if not raw and value.has_default:
                return value.default
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1]
            for option in options:
                if raw == str(option):
                    return option

    if prompt.repeat:
        hint = f" ({prompt.item_hint})" if prompt.item_hint else ""
        items: list[str] = []
        while True:
            raw = input_fn(f"{prompt.message}{hint} [blank to finish]: ")
            if not raw:
                if not items and value.has_default:
                    return value.default
                return items
            items.append(raw)

    while True:
        raw = input_fn(f"{prompt.message}{default_hint}: ")
        if raw or not value.has_default:
            return raw
        return value.default
