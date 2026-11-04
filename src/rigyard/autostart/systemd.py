"""Generate and manage only Rigyard-owned system services."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from ..errors import ScenarioExecutionError, ScenarioPlanError
from ..execution import CommandRunner, SubprocessRunner
from ..scenarios.runtime import ScenarioCommandGateway

MARKER = "# Rigyard autostart v1 "
UNIT_PATTERN = re.compile(r"rigyard-autostart-[a-f0-9]{64}\.service\Z")


def validate_unit(unit: str) -> str:
    if not UNIT_PATTERN.fullmatch(unit):
        raise ScenarioPlanError("invalid Rigyard autostart unit name")
    return unit


def quote(value: str, *, command: bool = False) -> str:
    """Systemd syntax, not shell quoting. Do not allow extra directives."""
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ScenarioPlanError("control characters cannot be stored in a systemd unit")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if command:
        value = value.replace("$", "$$")
    return '"' + value + '"'


def command_line(argv: tuple[str, ...]) -> str:
    return " ".join(quote(arg, command=True) for arg in argv)


class SystemdManager:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        directory: Path = Path("/etc/systemd/system"),
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.commands = ScenarioCommandGateway(self.runner)
        self.directory = directory

    def _privileged(self, *argv: str) -> None:
        prefix = () if os.geteuid() == 0 else ("sudo", "--")
        self.commands.checked((*prefix, *argv), "systemd operation failed")

    def metadata(self, unit: str) -> dict:
        path = self.directory / validate_unit(unit)
        try:
            first = path.read_text().splitlines()[0]
            if not first.startswith(MARKER):
                raise ValueError("not managed by Rigyard")
            result = json.loads(first[len(MARKER) :])
            if not isinstance(result, dict) or result.get("unit") != unit:
                raise ValueError("invalid metadata")
            return result
        except (OSError, ValueError, IndexError) as exc:
            raise ScenarioPlanError(f"cannot read Rigyard unit {unit}: {exc}") from exc

    def status(self, unit: str) -> str:
        validate_unit(unit)
        result = self.commands.checked(
            (
                "systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=LoadState,UnitFileState,ActiveState,SubState,Result",
            ),
            "cannot inspect systemd unit",
        )
        return result.stdout.strip()

    def stop(self, unit: str) -> None:
        self.metadata(unit)
        self._privileged("systemctl", "stop", unit)

    def disable(self, unit: str, *, now: bool = False) -> None:
        self.metadata(unit)
        self._privileged("systemctl", "disable", *(("--now",) if now else ()), unit)

    def install(self, unit: str, content: str, *, now: bool = False) -> None:
        destination = self.directory / validate_unit(unit)
        old = None
        enabled = False
        if destination.exists() or destination.is_symlink():
            self.metadata(unit)
            old = destination.read_text()
            state = self.status(unit)
            if any(
                f"ActiveState={value}" in state
                for value in ("active", "activating", "deactivating", "reloading")
            ):
                raise ScenarioPlanError("stop the running autostart service before updating it")
            enabled = "UnitFileState=enabled" in state
        with tempfile.TemporaryDirectory(prefix="rigyard-autostart-") as temporary:
            source = Path(temporary) / unit
            source.write_text(content)
            source.chmod(0o600)
            self.commands.checked(
                ("systemd-analyze", "verify", str(source)), "invalid autostart unit"
            )
            try:
                self._write(source, destination)
                self._privileged("systemctl", "daemon-reload")
                self._privileged("systemctl", "enable", unit)
            except BaseException as failure:
                try:
                    if old is None:
                        self._privileged("systemctl", "disable", unit)
                        self._privileged("rm", "-f", "--", str(destination))
                    else:
                        source.write_text(old)
                        self._write(source, destination)
                    self._privileged("systemctl", "daemon-reload")
                    if old is not None:
                        self._privileged("systemctl", "enable" if enabled else "disable", unit)
                except Exception as cleanup:
                    raise ScenarioExecutionError(
                        f"autostart installation failed; rollback also failed: {cleanup}"
                    ) from failure
                raise
        # A failed immediate start leaves the installed unit and journal available.
        if now:
            self._privileged("systemctl", "start", unit)

    def _write(self, source: Path, destination: Path) -> None:
        staging = destination.with_suffix(".service.new")
        try:
            self._privileged("install", "-m", "0644", "--", str(source), str(staging))
            self._privileged("mv", "-f", "--", str(staging), str(destination))
        finally:
            self._privileged("rm", "-f", "--", str(staging))
