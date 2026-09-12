"""Injectable process runner used by the Docker provider."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(
        self,
        command: tuple[str, ...],
        *,
        stdin: str | None = None,
        capture: bool = False,
    ) -> CommandResult:
        """Run a command without invoking a shell."""


class SubprocessRunner:
    def run(
        self,
        command: tuple[str, ...],
        *,
        stdin: str | None = None,
        capture: bool = False,
    ) -> CommandResult:
        completed = subprocess.run(
            command,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
