"""Validate a resolved container definition and create an immutable plan."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from ..errors import ContainerPlanError, SourceLocation
from .models import (
    ContainerHookPlan,
    ContainerHookSpec,
    ContainerMount,
    ContainerRunPlan,
    ContainerSpec,
    EnvironmentRef,
    LifecyclePhase,
)

MAX_HOOK_SCRIPT_BYTES = 1024 * 1024


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
        self._validate_workdir(spec.workdir, "workdir")
        resolved_environment = self._environment(spec.environment, environment, "environment")
        hooks = self._hooks(spec, config_path, environment, resolved_environment)
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
            resolved_environment,
            spec.command,
            hooks,
        )

    def _environment(
        self,
        configured: Mapping[str, str | EnvironmentRef],
        host: Mapping[str, str],
        field: str,
    ) -> tuple[tuple[str, str], ...]:
        resolved = []
        for env_name, source in sorted(configured.items()):
            if isinstance(source, EnvironmentRef):
                value = host.get(source.env, source.default)
                if value is None:
                    raise ContainerPlanError(
                        f"{field}.{env_name}: missing host environment {source.env!r}"
                    )
            else:
                value = source
            if "\x00" in value:
                raise ContainerPlanError(f"{field}.{env_name}: NUL bytes are not allowed")
            resolved.append((env_name, value))
        return tuple(resolved)

    def _hooks(
        self,
        spec: ContainerSpec,
        config_path: Path,
        environment: Mapping[str, str],
        container_environment: tuple[tuple[str, str], ...],
    ) -> tuple[ContainerHookPlan, ...]:
        planned = []
        for phase, hooks in (
            (LifecyclePhase.POST_CREATE, spec.lifecycle.post_create),
            (LifecyclePhase.POST_START, spec.lifecycle.post_start),
        ):
            for hook in hooks:
                planned.append(
                    self._hook(
                        phase,
                        hook,
                        config_path,
                        environment,
                        container_environment,
                    )
                )
        return tuple(planned)

    def _hook(
        self,
        phase: LifecyclePhase,
        hook: ContainerHookSpec,
        config_path: Path,
        environment: Mapping[str, str],
        container_environment: tuple[tuple[str, str], ...],
    ) -> ContainerHookPlan:
        field = f"lifecycle.{phase.value}.{hook.name}"
        script_path = self._project_path(config_path, hook.script)
        try:
            script_bytes = script_path.read_bytes()
        except OSError as exc:
            raise ContainerPlanError(
                f"{field}.script cannot be read: {exc}", SourceLocation(script_path)
            ) from exc
        if not script_bytes:
            raise ContainerPlanError(
                f"{field}.script must not be empty", SourceLocation(script_path)
            )
        if len(script_bytes) > MAX_HOOK_SCRIPT_BYTES:
            raise ContainerPlanError(
                f"{field}.script exceeds {MAX_HOOK_SCRIPT_BYTES} bytes",
                SourceLocation(script_path),
            )
        if b"\x00" in script_bytes:
            raise ContainerPlanError(
                f"{field}.script contains NUL bytes", SourceLocation(script_path)
            )
        try:
            script_content = script_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContainerPlanError(
                f"{field}.script must be UTF-8", SourceLocation(script_path)
            ) from exc
        if any(not item or "\x00" in item for item in hook.interpreter):
            raise ContainerPlanError(f"{field}.interpreter contains an invalid argument")
        if hook.user is not None and (not hook.user or "\x00" in hook.user):
            raise ContainerPlanError(f"{field}.user is invalid")
        self._validate_workdir(hook.workdir, f"{field}.workdir")
        hook_environment = self._environment(hook.environment, environment, f"{field}.environment")
        return ContainerHookPlan(
            phase=phase,
            name=hook.name,
            script_path=script_path,
            script_content=script_content,
            script_sha256=hashlib.sha256(script_bytes).hexdigest(),
            interpreter=hook.interpreter,
            user=hook.user,
            workdir=hook.workdir,
            environment=hook_environment,
            redact_values=tuple(
                dict.fromkeys(
                    value for _, value in (*container_environment, *hook_environment) if value
                )
            ),
            timeout_seconds=hook.timeout_seconds,
        )

    def _project_path(self, config_path: Path, configured: Path) -> Path:
        path = configured.expanduser()
        if not path.is_absolute():
            path = config_path.resolve().parent / path
        return path.resolve()

    def _validate_workdir(self, value: str | None, field: str) -> None:
        if value is not None and not PurePosixPath(value).is_absolute():
            raise ContainerPlanError(f"{field} must be absolute")

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
