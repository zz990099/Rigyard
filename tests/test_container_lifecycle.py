import hashlib
import subprocess
from pathlib import Path

import pytest

from rigyard.application.containers import CreateContainerUseCase
from rigyard.application.requests import ResolutionRequest
from rigyard.containers.models import (
    ContainerCreateResult,
    ContainerSpec,
    LifecyclePhase,
)
from rigyard.containers.planner import ContainerRunPlanner
from rigyard.containers.service import ContainerCreateService
from rigyard.errors import ContainerLifecycleError, ContainerPlanError
from rigyard.providers.docker.container_backend import DockerContainerBackend
from rigyard.providers.docker.runner import CommandResult


class QueueRunner:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[:2] == ("docker", "ps"):
            return CommandResult(0)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def lifecycle_plan(tmp_path: Path, *, secret: str = "host-secret"):
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    prepare = script_dir / "prepare.sh"
    prepare.write_text("echo prepare\n", encoding="utf-8")
    verify = script_dir / "verify.sh"
    verify.write_text("echo verify\n", encoding="utf-8")
    spec = ContainerSpec.model_validate(
        {
            "image": "cross-base:latest",
            "mounts": ["./sysroot:/opt/sysroot"],
            "environment": {"GLOBAL_SECRET": "container-secret"},
            "lifecycle": {
                "post_create": [
                    {
                        "name": "prepare-sysroot",
                        "script": "scripts/prepare.sh",
                        "interpreter": ["/bin/bash", "-eu"],
                        "user": "root",
                        "workdir": "/workspace",
                        "environment": {
                            "SYSROOT": "/opt/sysroot",
                            "TOKEN": {"env": "TOKEN"},
                        },
                        "timeout_seconds": 120,
                    }
                ],
                "post_start": [
                    {
                        "name": "verify-rigyard",
                        "script": "scripts/verify.sh",
                    }
                ],
            },
        }
    )
    return ContainerRunPlanner().plan(
        "cross-aarch64",
        spec,
        tmp_path / "rigyard.yaml",
        {"TOKEN": secret},
    )


def test_lifecycle_planner_orders_phases_and_freezes_script(tmp_path: Path):
    plan = lifecycle_plan(tmp_path)
    prepare, verify = plan.hooks
    assert [hook.phase for hook in plan.hooks] == [
        LifecyclePhase.POST_CREATE,
        LifecyclePhase.POST_START,
    ]
    assert prepare.script_path == (tmp_path / "scripts/prepare.sh")
    assert prepare.script_content == "echo prepare\n"
    assert prepare.script_sha256 == hashlib.sha256(b"echo prepare\n").hexdigest()
    assert prepare.environment == (("SYSROOT", "/opt/sysroot"), ("TOKEN", "host-secret"))
    assert prepare.redact_values == (
        "container-secret",
        "/opt/sysroot",
        "host-secret",
    )
    assert prepare.timeout_seconds == 120
    assert verify.interpreter == ("/bin/sh", "-eu")


@pytest.mark.parametrize(
    "hook,match",
    [
        ({"name": "missing", "script": "missing.sh"}, "cannot be read"),
        ({"name": "relative", "script": "ok.sh", "workdir": "relative"}, "must be absolute"),
        (
            {
                "name": "missing-env",
                "script": "ok.sh",
                "environment": {"TOKEN": {"env": "MISSING"}},
            },
            "missing host environment",
        ),
    ],
)
def test_invalid_hooks_fail_during_planning(tmp_path: Path, hook, match):
    (tmp_path / "ok.sh").write_text("true\n")
    spec = ContainerSpec.model_validate({"image": "ubuntu", "lifecycle": {"post_create": [hook]}})
    with pytest.raises(ContainerPlanError, match=match):
        ContainerRunPlanner().plan("dev", spec, tmp_path / "rigyard.yaml", {})


def test_service_runs_hooks_in_order_through_docker_exec(tmp_path: Path):
    plan = lifecycle_plan(tmp_path)
    runner = QueueRunner(
        CommandResult(0, "abc123\n"),
        CommandResult(0),
        CommandResult(0),
    )
    result = ContainerCreateService(DockerContainerBackend(runner)).create(plan)

    assert [(hook.phase, hook.name) for hook in result.hooks] == [
        (LifecyclePhase.POST_CREATE, "prepare-sysroot"),
        (LifecyclePhase.POST_START, "verify-rigyard"),
    ]
    prepare_command, prepare_options = runner.calls[2]
    assert prepare_command == (
        "docker",
        "exec",
        "-i",
        "--user=root",
        "--workdir=/workspace",
        "--env=SYSROOT=/opt/sysroot",
        "--env=TOKEN=host-secret",
        "abc123",
        "/bin/bash",
        "-eu",
    )
    assert prepare_options == {
        "stdin": "echo prepare\n",
        "capture": True,
        "timeout_seconds": 120,
    }


def test_failed_hook_reports_retained_container_and_redacts_environment(tmp_path: Path):
    plan = lifecycle_plan(tmp_path, secret="sensitive")
    runner = QueueRunner(
        CommandResult(0, "abc123\n"),
        CommandResult(9, stderr="failed with sensitive and container-secret"),
    )
    with pytest.raises(ContainerLifecycleError) as error:
        ContainerCreateService(DockerContainerBackend(runner)).create(plan)
    message = str(error.value)
    assert "was created" in message
    assert "post_create hook 'prepare-sysroot'" in message
    assert "kept for diagnosis" in message
    assert "sensitive" not in message
    assert "container-secret" not in message


def test_hook_timeout_reports_retained_container(tmp_path: Path):
    plan = lifecycle_plan(tmp_path)
    runner = QueueRunner(
        CommandResult(0, "abc123\n"),
        subprocess.TimeoutExpired(("docker", "exec"), 120),
    )
    with pytest.raises(ContainerLifecycleError, match="timed out.*kept for diagnosis"):
        ContainerCreateService(DockerContainerBackend(runner)).create(plan)


def test_values_file_can_target_prompt_inside_hook_array(tmp_path: Path):
    manifest = tmp_path / "rigyard.yaml"
    manifest.write_text(
        """version: 3
metadata: {name: lifecycle-test}
sources: {containers: config/containers.yaml}
"""
    )
    source = tmp_path / "config/containers.yaml"
    source.parent.mkdir()
    source.write_text(
        """cross-aarch64:
  image: cross-base
  lifecycle:
    post_create:
      - name: prepare
        script: scripts/prepare.sh
        user:
          default: root
          prompt: {mode: input, message: Hook user}
"""
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "prepare.sh").write_text("true\n")
    values = tmp_path / "values.yaml"
    values.write_text(
        """containers:
  cross-aarch64:
    lifecycle:
      post_create:
        - user: builder
"""
    )

    class UnusedBackend:
        def create(self, plan):
            return ContainerCreateResult(plan.container_name, "unused")

    plan = CreateContainerUseCase(UnusedBackend()).plan(
        "cross-aarch64",
        ResolutionRequest(manifest, values_path=values, interactive=False),
        environment={},
    )
    assert plan.hooks[0].user == "builder"
