import hashlib
import os
import shlex
import shutil
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
from rigyard.execution import CommandResult, SubprocessRunner
from rigyard.providers.docker.container_backend import DockerContainerBackend


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
    assert prepare_command[:8] == (
        "docker",
        "exec",
        "-i",
        "--user=root",
        "--workdir=/workspace",
        "--env=SYSROOT=/opt/sysroot",
        "--env=TOKEN=host-secret",
        "abc123",
    )
    assert prepare_command[-2:] == ("/bin/bash", "-eu")
    assert "rigyard-exec-" in prepare_command[-3]
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
        CommandResult(0),
    )
    with pytest.raises(ContainerLifecycleError, match="timed out.*kept for diagnosis"):
        ContainerCreateService(DockerContainerBackend(runner)).create(plan)


@pytest.mark.parametrize("interpreter", ["/bin/sh", "/bin/bash"])
@pytest.mark.parametrize("with_setsid", [False, True])
@pytest.mark.parametrize("exit_code", [0, 37])
def test_hook_executes_stdin_script_and_preserves_exit_status(
    tmp_path: Path, interpreter: str, with_setsid: bool, exit_code: int
):
    # Execute the real wrapper and interpreter; only replace the Docker transport.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    programs = ["rm", "setsid"] if with_setsid else ["rm"]
    for program in programs:
        executable = shutil.which(program)
        if executable is None:
            pytest.skip(f"{program} is unavailable")
        (bin_dir / program).symlink_to(executable)
    environment = {**os.environ, "PATH": str(bin_dir)}
    evidence = tmp_path / "hook-executed"
    script = tmp_path / "hook.sh"
    script.write_text(
        f"printf 'executed\\n' > {shlex.quote(str(evidence))}\n"
        "printf 'hook stdout\\n'\n"
        "printf 'hook stderr\\n' >&2\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    spec = ContainerSpec.model_validate(
        {
            "image": "test-image",
            "lifecycle": {
                "post_create": [
                    {"name": "prepare", "script": script, "interpreter": [interpreter, "-eu"]}
                ]
            },
        }
    )
    hook = ContainerRunPlanner().plan("dev", spec, tmp_path / "rigyard.yaml", {}).hooks[0]

    class LocalDockerExecRunner:
        def run(self, command, **kwargs):
            assert command[:4] == ("docker", "exec", "-i", "test-container")
            self.command = command
            self.result = SubprocessRunner().run(command[4:], environment=environment, **kwargs)
            return self.result

    runner = LocalDockerExecRunner()
    backend = DockerContainerBackend(runner)
    if exit_code:
        with pytest.raises(ContainerLifecycleError, match="exit 37: hook stderr"):
            backend.run_hook("dev", "test-container", hook)
    else:
        result = backend.run_hook("dev", "test-container", hook)
        assert (result.phase, result.name) == (LifecyclePhase.POST_CREATE, "prepare")

    assert evidence.read_text(encoding="utf-8") == "executed\n"
    assert runner.result == CommandResult(exit_code, "hook stdout\n", "hook stderr\n")
    marker = Path(runner.command[runner.command.index("rigyard-exec") + 1])
    assert not marker.exists()


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
