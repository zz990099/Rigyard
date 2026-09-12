"""Resolve container definitions without I/O or backend calls."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from ..errors import ContainerPlanError
from ..parameters.context import ResolvedContext
from ..parameters.references import ParameterRef
from .models import (
    ContainerMount,
    ContainerRunPlan,
    ContainerSpec,
    EnvironmentRef,
    ValueSource,
)


class ContainerRunPlanner:
    def plan(
        self,
        key: str,
        spec: ContainerSpec,
        context: ResolvedContext,
        config_path: Path,
        environment: Mapping[str, str],
    ) -> ContainerRunPlan:
        def resolve(source: ValueSource, field: str, *, empty: bool = False) -> str:
            value: object = source
            if isinstance(source, ParameterRef):
                if source.parameter not in context:
                    raise ContainerPlanError(f"{field}: unresolved parameter {source.parameter!r}")
                value = context[source.parameter]
            elif isinstance(source, EnvironmentRef):
                value = environment.get(source.env, source.default)
                if value is None:
                    raise ContainerPlanError(f"{field}: missing host environment {source.env!r}")
            if not isinstance(value, (str, int, float, bool, Path)):
                raise ContainerPlanError(f"{field}: expected a scalar value")
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            if "\x00" in rendered or (not empty and not rendered):
                raise ContainerPlanError(f"{field}: empty values or NUL bytes are not allowed")
            return rendered

        def optional(source: ValueSource | None, field: str) -> str | None:
            return None if source is None else resolve(source, field)

        name = resolve(spec.name if spec.name is not None else key, "name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ContainerPlanError("invalid container name")
        image = resolve(spec.image, "image")
        if image.startswith("-") or any(char.isspace() for char in image):
            raise ContainerPlanError("image must be one image reference, not flags or a command")
        mounts = []
        targets = set()
        for mount in spec.mounts:
            source = resolve(mount.source, "mount.source")
            target = resolve(mount.target, "mount.target")
            if not PurePosixPath(target).is_absolute():
                raise ContainerPlanError("mount.target must be absolute")
            target = str(PurePosixPath(target))
            if target in targets:
                raise ContainerPlanError(f"duplicate mount target {target!r}")
            targets.add(target)
            if mount.type == "bind":
                source = str((config_path.resolve().parent / source).resolve())
            elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source):
                raise ContainerPlanError("invalid named volume")
            if any(char in source + target for char in ",\n\r"):
                raise ContainerPlanError("mount paths must not contain commas or newlines")
            mounts.append(ContainerMount(mount.type, source, target, mount.read_only))
        devices = tuple(resolve(value, "device") for value in spec.devices)
        for device in devices:
            parts = device.split(":")
            if len(parts) > 3 or any(not part.startswith("/") for part in parts[:2]):
                raise ContainerPlanError("device must be /host/path[:/container/path[:rwm]]")
            if len(parts) == 3 and not re.fullmatch(r"[rwm]+", parts[2]):
                raise ContainerPlanError("invalid device permissions")
        workdir = optional(spec.workdir, "workdir")
        if workdir is not None and not PurePosixPath(workdir).is_absolute():
            raise ContainerPlanError("workdir must be absolute")
        return ContainerRunPlan(
            name,
            image,
            spec.interactive,
            spec.tty,
            spec.privileged,
            devices,
            tuple(resolve(value, "group_add") for value in spec.group_add),
            tuple(mounts),
            optional(spec.network, "network"),
            optional(spec.ipc, "ipc"),
            workdir,
            tuple(
                (key, resolve(value, f"environment.{key}", empty=True))
                for key, value in sorted(spec.environment.items())
            ),
            tuple(resolve(value, "command", empty=True) for value in spec.command),
        )
