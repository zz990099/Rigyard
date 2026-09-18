from pathlib import Path

from toolchain.cli.main import run
from toolchain.images.models import BuildStepResult


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def config_file(tmp_path: Path) -> Path:
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 3
metadata: {name: test-project}
sources:
  images: config/images.yaml
  containers: config/containers.yaml
""",
    )
    write(
        tmp_path / "config/images.yaml",
        """development:
  base:
    default: ubuntu:22.04
    prompt:
      mode: select
      message: Select base
      options: [ubuntu:22.04, ubuntu:24.04]
  tag: example/development:latest
  layers: [{name: system, dockerfile: system.Dockerfile}]
""",
    )
    write(
        tmp_path / "config/containers.yaml",
        """development:
  image: ubuntu:24.04
  privileged:
    default: false
    prompt: {mode: confirm, message: "Privileged?"}
""",
    )
    return config


def test_validate_and_inspect_use_global_project_config(tmp_path: Path, capsys):
    config = config_file(tmp_path)
    assert run(["--config", str(config), "validate"]) == 0
    assert "OK:" in capsys.readouterr().out
    assert run(["--config", str(config), "inspect", "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert '"images.development.base"' in output
    assert '"mode": "select"' in output


def test_resolve_nested_values_and_cli_override(tmp_path: Path, capsys):
    config = config_file(tmp_path)
    values = write(
        tmp_path / "values.yaml",
        """images:
  development:
    base: ubuntu:24.04
containers:
  development:
    privileged: false
""",
    )
    assert (
        run(
            [
                "--config",
                str(config),
                "resolve",
                "--values",
                str(values),
                "--set",
                "containers.development.privileged=true",
                "--non-interactive",
                "--with-sources",
                "--format",
                "json",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"value": true' in output and '"source": "cli"' in output


def test_noninteractive_missing_runtime_value(tmp_path: Path, capsys):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 3
metadata: {name: test-project}
sources: {containers: config/containers.yaml}
""",
    )
    write(
        tmp_path / "config/containers.yaml",
        """dev:
  image:
    prompt: {mode: input, message: Image}
""",
    )
    assert run(["--config", str(config), "container", "create", "dev", "--non-interactive"]) == 3
    assert "missing required" in capsys.readouterr().err


def test_image_build_resolves_only_selected_image(tmp_path: Path, monkeypatch, capsys):
    config = config_file(tmp_path)
    write(tmp_path / "system.Dockerfile", "RUN echo system\n")

    class FakeBackend:
        def __init__(self):
            self.steps = []

        def check_available(self):
            pass

        def build_step(self, step):
            self.steps.append(step)
            return BuildStepResult(step.index, step.layer_name, step.output_tag, ("fake",))

    backend = FakeBackend()
    monkeypatch.setattr("toolchain.cli.commands.images.DockerImageBackend", lambda: backend)
    assert (
        run(
            [
                "--config",
                str(config),
                "image",
                "build",
                "development",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert backend.steps[0].base_image == "ubuntu:22.04"
    assert backend.steps[0].context == tmp_path
    assert "Built example/development:latest" in capsys.readouterr().out


def test_image_build_source_disambiguates_duplicate_names(tmp_path: Path, monkeypatch, capsys):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 3
metadata: {name: duplicate-images}
sources:
  images:
    - config/a.yaml
    - config/b.yaml
""",
    )
    write(
        tmp_path / "config/a.yaml",
        """x86_64_dev:
  base: ubuntu:22.04
  tag: example/a:latest
  layers: [{name: system, dockerfile: system.Dockerfile}]
""",
    )
    write(
        tmp_path / "config/b.yaml",
        """x86_64_dev:
  base: ubuntu:24.04
  tag: example/b:latest
  layers: [{name: system, dockerfile: system.Dockerfile}]
""",
    )
    write(tmp_path / "system.Dockerfile", "RUN echo system\n")

    class FakeBackend:
        def __init__(self):
            self.steps = []

        def check_available(self):
            pass

        def build_step(self, step):
            self.steps.append(step)
            return BuildStepResult(step.index, step.layer_name, step.output_tag, ("fake",))

    backend = FakeBackend()
    monkeypatch.setattr("toolchain.cli.commands.images.DockerImageBackend", lambda: backend)
    assert (
        run(
            [
                "--config",
                str(config),
                "image",
                "build",
                "x86_64_dev",
                "--source",
                "config/b.yaml",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert backend.steps[0].base_image == "ubuntu:24.04"
    assert "Built example/b:latest" in capsys.readouterr().out


def test_selected_operation_accepts_values_for_other_operations(tmp_path: Path, monkeypatch):
    config = config_file(tmp_path)
    write(tmp_path / "system.Dockerfile", "RUN echo system\n")
    values = write(
        tmp_path / "values.yaml",
        """images: {development: {base: ubuntu:24.04}}
containers: {development: {privileged: true}}
""",
    )

    class FakeBackend:
        def check_available(self):
            pass

        def build_step(self, step):
            return BuildStepResult(step.index, step.layer_name, step.output_tag, ("fake",))

    monkeypatch.setattr("toolchain.cli.commands.images.DockerImageBackend", FakeBackend)
    assert (
        run(
            [
                "--config",
                str(config),
                "image",
                "build",
                "development",
                "--values",
                str(values),
                "--non-interactive",
            ]
        )
        == 0
    )
