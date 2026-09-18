"""Small testable terminal I/O adapter; deliberately not a full-screen TUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TextIO

from ..style import Line, Style


class MenuIO:
    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        style: Style | None = None,
    ) -> None:
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.style = style or Style.for_stream(self.output)

    @property
    def is_interactive(self) -> bool:
        return self.input.isatty() and self.output.isatty()

    def write(self, message: str = "") -> None:
        print(message, file=self.output)

    def write_field(self, message: Line | str) -> None:
        """Print one ``Key: value`` plan line with the field name dimmed."""

        self.write(
            message.render(self.style) if isinstance(message, Line) else self.style.line(message)
        )

    def write_note(self, message: str, role: str = "warning") -> None:
        self.write(self.style.render(role, message))

    def ask(self, prompt: str) -> str:
        self.output.write(prompt)
        self.output.flush()
        line = self.input.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\r\n")

    def select(
        self,
        title: str | None,
        options: Sequence[str],
        *,
        back_label: str,
    ) -> int | None:
        while True:
            self.write()
            if title:
                self.write(self.style.render("title", title))
                self.write()
            for index, label in enumerate(options, start=1):
                self.write(f"{self.style.render('number', f'{index})')} {label}")
            self.write(self.style.render("muted", f"0) {back_label}"))
            raw = self.ask(self.style.render("muted", f"Select [0-{len(options)}]: ")).strip()
            if raw.isdigit():
                choice = int(raw)
                if choice == 0:
                    return None
                if 1 <= choice <= len(options):
                    return choice - 1
            self.write(f"Invalid selection: {raw!r}")

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        question = f"{self.style.render('heading', prompt)} [{self.style.render('muted', hint)}]: "
        while True:
            value = self.ask(question).strip().lower()
            if not value:
                return default
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            self.write("Enter y or n.")
