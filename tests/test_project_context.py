from datetime import datetime, timezone
from pathlib import Path

import pytest

from rigyard.application.builds import BuildProjectUseCase
from rigyard.application.project import ProjectContext
from rigyard.application.requests import BuildImageRequest, ResolutionRequest


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_project_context_keeps_config_environment_and_time_in_one_snapshot(tmp_path: Path):
    config_path = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: snapshot-test}
sources: {builds: builds.yaml}
""",
    )
    builds_path = write(
        tmp_path / "builds.yaml",
        """native:
  container: dev_${env:USER}_${date:%Y}
  script: /workspace/build.sh
""",
    )
    captured_at = datetime(2026, 9, 21, tzinfo=timezone.utc)
    project = ProjectContext.capture(
        config_path,
        environment={"USER": "alice"},
        timestamp=captured_at,
    )

    write(
        builds_path,
        """native:
  container: changed
  script: /workspace/changed.sh
""",
    )
    plan = BuildProjectUseCase(backend=None).plan(
        "native",
        ResolutionRequest(config_path, interactive=False, project=project),
    )

    assert plan.container == "dev_alice_2026"
    assert plan.script == Path("/workspace/build.sh")
    assert project.timestamp is captured_at
    with pytest.raises(TypeError):
        project.environment["USER"] = "bob"


def test_build_image_request_preserves_project_context(tmp_path: Path):
    config_path = write(
        tmp_path / "rigyard.yaml",
        "version: 3\nmetadata: {name: snapshot-test}\nsources: {builds: builds.yaml}\n",
    )
    write(tmp_path / "builds.yaml", "native: {container: dev, script: /build.sh}\n")
    project = ProjectContext.capture(config_path, environment={})

    request = BuildImageRequest(config_path, "development", project=project).resolution_request()

    assert request.project is project


def test_runtime_environment_uses_the_same_snapshot_as_templates(tmp_path: Path, monkeypatch):
    config_path = write(
        tmp_path / "rigyard.yaml",
        "version: 3\nmetadata: {name: snapshot-test}\nsources: {builds: builds.yaml}\n",
    )
    write(
        tmp_path / "builds.yaml",
        """native:
  container:
    prompt: {mode: input, message: Container}
  script: /workspace/${env:USER}/build.sh
""",
    )
    parameter = "RIGYARD_PARAM_BUILDS_NATIVE_CONTAINER"
    project = ProjectContext.capture(
        config_path,
        environment={"USER": "alice", parameter: "dev-alice"},
    )
    monkeypatch.setenv("USER", "bob")
    monkeypatch.setenv(parameter, "dev-bob")

    use_case = BuildProjectUseCase(backend=None)
    request = ResolutionRequest(config_path, interactive=False, project=project)
    plan = use_case.plan("native", request)
    override = use_case.plan(
        "native",
        request,
        environment={"USER": "charlie", parameter: "dev-charlie"},
    )

    assert (plan.container, plan.script) == ("dev-alice", Path("/workspace/alice/build.sh"))
    assert (override.container, override.script) == (
        "dev-charlie",
        Path("/workspace/charlie/build.sh"),
    )
