import io
from pathlib import Path

from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.errors import ImageBuildError
from toolchain.images.models import BuildStepResult


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class InterruptingTTY(TTYBuffer):
    def readline(self, *args, **kwargs):
        raise KeyboardInterrupt


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(
    tmp_path: Path,
    *,
    images: str | None = None,
    containers: str | None = None,
) -> Path:
    sources = []
    if images is not None:
        sources.append("  images: config/images.yaml")
        write(tmp_path / "config/images.yaml", images)
    if containers is not None:
        sources.append("  containers: config/containers.yaml")
        write(tmp_path / "config/containers.yaml", containers)
    return write(
        tmp_path / "toolchain.yaml",
        "version: 2\nmetadata: {name: menu-test}\nsources:\n" + "\n".join(sources) + "\n",
    )


def prompt_config(tmp_path: Path) -> Path:
    return project(
        tmp_path,
        containers="""dev:
  image: ubuntu
  network:
    default: host
    prompt:
      mode: select
      message: Select network
      options: [host, bridge]
""",
    )


def test_bare_command_enters_primary_action_menu_only_for_tty(tmp_path: Path):
    config = prompt_config(tmp_path)
    output = TTYBuffer()
    assert run(["--config", str(config)], stdin=TTYBuffer("0\n"), stdout=output) == 0
    rendered = output.getvalue()
    assert "1) Build image [no images configured]" in rendered
    assert "2) Create container" in rendered
    assert "3) Build project [no builds configured]" in rendered
    assert "4) Start scene [no scenarios configured]" in rendered
    assert "Configure parameters" not in rendered
    assert "Show effective parameters" not in rendered
    assert "Validate configuration" not in rendered


def test_non_tty_bare_command_prints_help_without_loading_config():
    output = io.StringIO()
    assert run([], stdin=io.StringIO(), stdout=output) == 2
    assert "usage: toolchain" in output.getvalue()


def test_image_menu_executes_once_and_exits(tmp_path: Path):
    config = project(
        tmp_path,
        images="""development:
  description: Development environment
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
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("1\n1\n2\ny\n"), output), backend_factory=lambda: backend)
    assert app.run(config) == 0
    assert backend.steps[0].base_image == "ubuntu:24.04"
    assert output.getvalue().count("Configuration:") == 1


def test_failed_menu_action_exits_with_backend_error(tmp_path: Path, monkeypatch):
    config = project(
        tmp_path,
        images="""development:
  base: ubuntu
  tag: example/development
  layers: [{name: system, dockerfile: system.Dockerfile}]
""",
    )
    write(tmp_path / "system.Dockerfile", "RUN false\n")

    class FailingBackend:
        def check_available(self):
            pass

        def build_step(self, step):
            raise ImageBuildError("failed")

    monkeypatch.setattr("toolchain.cli.menu.app.DockerImageBackend", FailingBackend)
    output = TTYBuffer()
    error = io.StringIO()
    assert (
        run(
            ["--config", str(config)],
            stdin=TTYBuffer("1\n1\ny\n"),
            stdout=output,
            stderr=error,
        )
        == 4
    )
    assert output.getvalue().count("Configuration:") == 1
    assert "Error: failed" in error.getvalue()


def test_invalid_selection_and_interrupt(tmp_path: Path):
    config = prompt_config(tmp_path)
    output = TTYBuffer()
    assert MenuApp(MenuIO(TTYBuffer("bad\n0\n"), output)).run(config) == 0
    assert "Invalid selection" in output.getvalue()
    output = TTYBuffer()
    assert MenuApp(MenuIO(InterruptingTTY(), output)).run(config) == 130
