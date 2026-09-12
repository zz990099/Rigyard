import io
from pathlib import Path

from toolchain.cli.main import run
from toolchain.cli.menu.app import MenuApp
from toolchain.cli.menu.prompt import MenuIO
from toolchain.images.models import BuildStepResult


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class InterruptingTTY(TTYBuffer):
    def readline(self, *args, **kwargs):
        raise KeyboardInterrupt


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "toolchain.yaml"
    path.write_text(body)
    return path


def prompt_config(tmp_path: Path) -> Path:
    return write_config(
        tmp_path,
        """version: 1
containers:
  dev:
    image: ubuntu
    network:
      default: host
      prompt:
        mode: select
        message: Select network
        options: [host, bridge]
""",
    )


def test_bare_command_enters_menu_only_for_tty(tmp_path: Path):
    config = prompt_config(tmp_path)
    output = TTYBuffer()
    assert run(["--config", str(config)], stdin=TTYBuffer("0\n"), stdout=output) == 0
    assert "1) Build image [no images configured]" in output.getvalue()


def test_non_tty_bare_command_prints_help_without_loading_config():
    output = io.StringIO()
    assert run([], stdin=io.StringIO(), stdout=output) == 2
    assert "usage: toolchain" in output.getvalue()


def test_menu_edits_inline_prompt_as_session_override(tmp_path: Path):
    config = prompt_config(tmp_path)
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("2\n1\n2\n0\n3\n0\n"), output))
    assert app.run(config) == 0
    assert "containers.dev.network = bridge [session]" in output.getvalue()
    assert config.read_text().count("bridge") == 1


def test_menu_values_file_is_shown_without_prompting(tmp_path: Path):
    config = prompt_config(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("containers: {dev: {network: bridge}}\n")
    output = TTYBuffer()
    assert MenuApp(MenuIO(TTYBuffer("3\n0\n"), output)).run(config, values) == 0
    assert "containers.dev.network = bridge [values]" in output.getvalue()


def test_image_menu_resolves_inline_select_prompt(tmp_path: Path):
    config = write_config(
        tmp_path,
        """version: 1
images:
  development:
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
    (tmp_path / "system.Dockerfile").write_text("RUN echo system\n")

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
    app = MenuApp(MenuIO(TTYBuffer("1\n1\n2\ny\n0\n"), output), backend_factory=lambda: backend)
    assert app.run(config) == 0
    assert backend.steps[0].base_image == "ubuntu:24.04"


def test_invalid_selection_and_interrupt(tmp_path: Path):
    config = prompt_config(tmp_path)
    output = TTYBuffer()
    assert MenuApp(MenuIO(TTYBuffer("bad\n0\n"), output)).run(config) == 0
    assert "Invalid selection" in output.getvalue()
    output = TTYBuffer()
    assert MenuApp(MenuIO(InterruptingTTY(), output)).run(config) == 130
