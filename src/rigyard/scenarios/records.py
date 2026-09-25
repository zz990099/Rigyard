"""Atomic, private scenario control records; no executable group configuration is stored."""

from __future__ import annotations

import fcntl
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ..errors import ScenarioExecutionError, ScenarioPlanError
from .models import ScenarioControlPlan


class ScenarioRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    state: Literal["starting", "running", "failed", "stopped"]
    target: ScenarioControlPlan


class FileRunStore:
    """Serialize lifecycle writes per project and atomically replace individual records."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.directory = self.config_path.parent / ".rigyard" / "runs"

    @contextmanager
    def locked(self) -> Iterator[None]:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (self.directory / ".lock").open("a") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)
        except OSError as exc:
            raise ScenarioExecutionError(f"cannot lock scenario records: {exc}") from exc

    def records(self) -> tuple[ScenarioRunRecord, ...]:
        result = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                record = ScenarioRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError) as exc:
                raise ScenarioExecutionError(f"cannot read scenario record {path}: {exc}") from exc
            identity = record.target.identity
            if identity is None or identity.key != path.stem:
                raise ScenarioExecutionError(f"invalid scenario record identity: {path}")
            if identity.config_path.resolve() == self.config_path:
                result.append(record)
        return tuple(result)

    def find(
        self,
        scene: str,
        profile: str | None,
        source: Path | None,
    ) -> ScenarioRunRecord | None:
        source_path = (
            None if source is None else (self.config_path.parent / source.expanduser()).resolve()
        )
        matches = [
            record
            for record in self.records()
            if record.target.scene_name == scene
            and (profile is None or record.target.profile_name == profile)
            and (
                source_path is None
                or (
                    record.target.identity is not None
                    and record.target.identity.source_path == source_path
                )
            )
        ]
        if len(matches) > 1:
            raise ScenarioPlanError("ambiguous recorded scenario; select a profile and --source")
        return matches[0] if matches else None

    def write(self, record: ScenarioRunRecord) -> None:
        identity = record.target.identity
        if identity is None:
            raise ScenarioPlanError("cannot record a scenario without an identity")
        temporary: str | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                delete=False,
                prefix=".run-",
            ) as stream:
                temporary = stream.name
                os.chmod(temporary, 0o600)
                stream.write(record.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / f"{identity.key}.json")
        except OSError as exc:
            raise ScenarioExecutionError(f"cannot save scenario record: {exc}") from exc
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def remove(self, target: ScenarioControlPlan) -> None:
        if target.identity is not None:
            try:
                (self.directory / f"{target.identity.key}.json").unlink(missing_ok=True)
            except OSError as exc:
                raise ScenarioExecutionError(f"cannot remove scenario record: {exc}") from exc


def select_recorded_target(
    record: ScenarioRunRecord,
    instances: Sequence[str] | None,
) -> ScenarioControlPlan:
    target = record.target
    if not instances:
        return replace(target, partial=False)
    names = {item.name for item in target.instances}
    missing = set(instances) - names
    if missing:
        raise ScenarioPlanError("unknown recorded instance(s): " + ", ".join(sorted(missing)))
    return replace(
        target,
        partial=True,
        instances=tuple(item for item in target.instances if item.name in instances),
    )
