"""Validate a resolved container definition and create an immutable plan."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from ..errors import ContainerPlanError
from .models import ContainerMount, ContainerRunPlan, ContainerSpec, EnvironmentRef


class ContainerRunPlanner:
    def plan(
        self,
        key: str,
        spec: ContainerSpec,
        config_path: Path,
        environment: Mapping[str, str],
    ) -> ContainerRunPlan:
        name = spec.name or key
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ContainerPlanError("invalid container name")
        if not spec.image or spec.image.startswith("-") or any(c.isspace() for c in spec.image):
            raise ContainerPlanError("image must be one image reference, not flags or a command")
        mounts = self._mounts(spec.mounts, config_path)
        for device in spec.devices:
            parts = device.split(":")
            if len(parts) > 3 or any(not part.startswith("/") for part in parts[:2]):
                raise ContainerPlanError("device must be /host/path[:/container/path[:rwm]]")
            if len(parts) == 3 and not re.fullmatch(r"[rwm]+", parts[2]):
                raise ContainerPlanError("invalid device permissions")
        if spec.workdir is not None and not PurePosixPath(spec.workdir).is_absolute():
            raise ContainerPlanError("workdir must be absolute")
        resolved_environment = []
        for env_name, source in sorted(spec.environment.items()):
            if isinstance(source, EnvironmentRef):
                value = environment.get(source.env, source.default)
                if value is None:
                    raise ContainerPlanError(
                        f"environment.{env_name}: missing host environment {source.env!r}"
                    )
            else:
                value = source
            if "\x00" in value:
                raise ContainerPlanError(f"environment.{env_name}: NUL bytes are not allowed")
            resolved_environment.append((env_name, value))
        return ContainerRunPlan(
            name,
            spec.image,
            spec.interactive,
            spec.tty,
            spec.privileged,
            spec.devices,
            spec.group_add,
            mounts,
            spec.network,
            spec.ipc,
            spec.workdir,
            tuple(resolved_environment),
            spec.command,
        )

    def _mounts(self, configured: tuple[str, ...], config_path: Path) -> tuple[ContainerMount, ...]:
        mounts = []
        targets = set()
        for value in configured:
            if any(character in value for character in "\x00\n\r,"):
                raise ContainerPlanError(
                    "mount values must not contain commas or control characters"
                )
            parts = value.split(":")
            if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
                raise ContainerPlanError(f"invalid mount {value!r}; expected SOURCE:TARGET[:ro]")
            source, target = parts[:2]
            option = parts[2] if len(parts) == 3 else "rw"
            if option not in {"ro", "rw"}:
                raise ContainerPlanError(f"invalid mount option {option!r}; expected ro or rw")
            target_path = PurePosixPath(target)
            if not target_path.is_absolute():
                raise ContainerPlanError(f"mount target must be absolute: {target!r}")
            target = str(target_path)
            if target in targets:
                raise ContainerPlanError(f"duplicate mount target {target!r}")
            targets.add(target)
            is_bind = source.startswith(("/", ".", "~"))
            if is_bind:
                source_path = Path(source).expanduser()
                if not source_path.is_absolute():
                    source_path = config_path.resolve().parent / source_path
                source = str(source_path.resolve())
                mount_type = "bind"
            else:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source):
                    raise ContainerPlanError(f"invalid named volume {source!r}")
                mount_type = "volume"
            mounts.append(ContainerMount(mount_type, source, target, option == "ro"))
        return tuple(mounts)
