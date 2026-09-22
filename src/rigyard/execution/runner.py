"""Injectable subprocess runner shared by host-side providers."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
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
        timeout_seconds: int | None = None,
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run argv directly without invoking a shell."""
        raise NotImplementedError


class SubprocessRunner:
    def run(
        self,
        command: tuple[str, ...],
        *,
        stdin: str | None = None,
        capture: bool = False,
        timeout_seconds: int | None = None,
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            command,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=False,
            timeout=timeout_seconds,
            cwd=cwd,
            env=environment,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
