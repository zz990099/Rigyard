"""Small testable terminal I/O adapter; deliberately not a full-screen TUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TextIO


class MenuIO:
    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout

    @property
    def is_interactive(self) -> bool:
        return self.input.isatty() and self.output.isatty()

    def write(self, message: str = "") -> None:
        print(message, file=self.output)

    def ask(self, prompt: str) -> str:
        self.output.write(prompt)
        self.output.flush()
        line = self.input.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\r\n")

    def select(
        self,
        title: str,
        options: Sequence[str],
        *,
        back_label: str,
    ) -> int | None:
        while True:
            self.write()
            self.write(title)
            self.write()
            for index, label in enumerate(options, start=1):
                self.write(f"{index}) {label}")
            self.write(f"0) {back_label}")
            raw = self.ask(f"Select [0-{len(options)}]: ").strip()
            if raw.isdigit():
                choice = int(raw)
                if choice == 0:
                    return None
                if 1 <= choice <= len(options):
                    return choice - 1
            self.write(f"Invalid selection: {raw!r}")

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        while True:
            value = self.ask(f"{prompt} [{hint}]: ").strip().lower()
            if not value:
                return default
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            self.write("Enter y or n.")
