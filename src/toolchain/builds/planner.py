"""Turn a resolved build definition into a deterministic host execution plan."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ..errors import BuildPlanError, SourceLocation
from .models import BuildPlan, BuildSpec


class BuildPlanner:
    def create_plan(
        self,
        build_name: str,
        spec: BuildSpec,
        config_path: str | Path,
        environment: Mapping[str, str] | None = None,
    ) -> BuildPlan:
        config_file = Path(config_path).resolve()
        project_dir = config_file.parent
        script = _resolve_path(project_dir, spec.script)
        workdir = _resolve_path(project_dir, spec.workdir)

        if not script.is_file():
            raise BuildPlanError(
                f"build {build_name!r} script is not a file: {script}",
                SourceLocation(config_file),
            )
        if not os.access(script, os.R_OK):
            raise BuildPlanError(
                f"build {build_name!r} script is not readable: {script}",
                SourceLocation(config_file),
            )
        if not workdir.is_dir():
            raise BuildPlanError(
                f"build {build_name!r} workdir is not a directory: {workdir}",
                SourceLocation(config_file),
            )

        inherited = dict(os.environ if environment is None else environment)
        inherited.update(spec.environment)
        return BuildPlan(
            build_name=build_name,
            script=script,
            command=(*spec.interpreter, str(script)),
            workdir=workdir,
            environment=tuple(sorted(inherited.items())),
            environment_overrides=tuple(sorted(spec.environment)),
            timeout_seconds=spec.timeout_seconds,
        )


def _resolve_path(project_dir: Path, configured: Path) -> Path:
    path = configured.expanduser()
    return (project_dir / path).resolve() if not path.is_absolute() else path.resolve()
