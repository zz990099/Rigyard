"""Terminal acquisition for inline prompt values."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .models import PromptMode, PromptSpec, PromptValue
from .sources import DynamicOption

InputFunction = Callable[[str], str]


def prompt_for_value(
    value: PromptValue,
    input_fn: InputFunction = input,
    *,
    default_display: str | None = None,
    dynamic_options: Sequence[DynamicOption] | None = None,
) -> Any:
    """Acquire one prompt value from the terminal.

    ``default_display`` is the default as it should be shown to the user, i.e. already
    expanded through the string templates (``${env:USER}`` → ``root``). When it is
    omitted the raw default is displayed; prompts without a default show no hint.
    The value returned for an accepted default stays the raw one: it is rendered once
    more together with the rest of the selected definition.

    ``dynamic_options`` replaces the configured ``options`` of a select prompt with
    candidates looked up at runtime (for example the existing containers). Such a
    source is an open set: an answer that is not in the list is used as the value.
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
        values, prompt_text = _select_values_and_prompt(prompt, default_hint, dynamic_options)
        while True:
            raw = input_fn(prompt_text).strip()
            if not raw and value.has_default:
                return value.default
            if raw.isdigit() and 1 <= int(raw) <= len(values):
                return values[int(raw) - 1]
            for candidate in values:
                if raw == str(candidate):
                    return candidate
            if dynamic_options is not None:
                return raw

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


def _select_values_and_prompt(
    prompt: PromptSpec,
    default_hint: str,
    dynamic_options: Sequence[DynamicOption] | None,
) -> tuple[tuple[Any, ...], str]:
    """Return the selectable values and the text shown for this select prompt."""

    if dynamic_options is None:
        options = tuple(prompt.options or ())
        choices = ", ".join(f"{index}={option}" for index, option in enumerate(options, 1))
        shown = f" ({choices})" if choices else ""
        return options, f"{prompt.message}{shown}{default_hint}: "
    return (
        tuple(option.value for option in dynamic_options),
        _dynamic_select_prompt(prompt, dynamic_options, default_hint),
    )


def _dynamic_select_prompt(
    prompt: PromptSpec,
    dynamic_options: Sequence[DynamicOption],
    default_hint: str,
) -> str:
    """List runtime candidates one per line, aligned by name, then ask the question."""

    question = f"{prompt.message}{default_hint}: "
    if not dynamic_options:
        return question
    width = max(len(option.value) for option in dynamic_options)
    entries = (
        "  {index}) {value:<{width}}{details}".format(
            index=index,
            value=option.value,
            width=width,
            details=f"  {option.label}" if option.label else "",
        )
        for index, option in enumerate(dynamic_options, 1)
    )
    return (
        "\n".join((*entries, question))
    )
