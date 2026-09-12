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
    path.write_text(body, encoding="utf-8")
    return path


def parameter_config(tmp_path: Path) -> Path:
    return write_config(
        tmp_path,
        """\
version: 1
parameters:
  target:
    type: choice
    options: [simulation, hardware]
    default: simulation
  count:
    type: int
    default: 1
""",
    )


def test_bare_command_enters_menu_only_for_tty(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    output = TTYBuffer()
    assert run(["--config", str(config)], stdin=TTYBuffer("0\n"), stdout=output) == 0
    assert "1) Build image [no images configured]" in output.getvalue()


def test_non_tty_bare_command_prints_help_without_loading_config() -> None:
    output = io.StringIO()
    assert run([], stdin=io.StringIO(), stdout=output) == 2
    assert "usage: toolchain" in output.getvalue()


def test_invalid_selection_retries(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("bad\n9\n0\n"), output))
    assert app.run(config) == 0
    assert output.getvalue().count("Invalid selection") == 2


def test_parameter_override_is_session_scoped_and_visible(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    output = TTYBuffer()
    # Configure parameters -> target -> hardware -> back -> show -> exit.
    answers = TTYBuffer("2\n1\n2\n0\n3\n0\n")
    app = MenuApp(MenuIO(answers, output))
    assert app.run(config) == 0
    rendered = output.getvalue()
    assert "target = hardware [session]" in rendered
    assert config.read_text(encoding="utf-8").count("hardware") == 1


def test_menu_values_file_participates_in_resolution(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("count: 7\n", encoding="utf-8")
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("3\n0\n"), output))
    assert app.run(config, values) == 0
    assert "count = 7 [values]" in output.getvalue()


def test_unavailable_action_explains_reason(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("1\n0\n"), output))
    assert app.run(config) == 0
    assert "Unavailable: no images configured" in output.getvalue()


def test_image_menu_calls_shared_build_use_case(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """\
version: 1
images:
  development:
    description: Development environment
    base: ubuntu:22.04
    tag: example/development:latest
    layers:
      - name: system
        dockerfile: system.Dockerfile
""",
    )
    (tmp_path / "system.Dockerfile").write_text("RUN echo system\n", encoding="utf-8")

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
    app = MenuApp(
        MenuIO(TTYBuffer("1\n1\ny\n0\n"), output),
        backend_factory=lambda: backend,
    )
    assert app.run(config) == 0
    assert [step.layer_name for step in backend.steps] == ["system"]
    assert "development — Development environment" in output.getvalue()
    assert "Built example/development:latest (1 layer(s))" in output.getvalue()


def test_ctrl_c_at_main_menu_returns_130(tmp_path: Path) -> None:
    config = parameter_config(tmp_path)
    output = TTYBuffer()
    app = MenuApp(MenuIO(InterruptingTTY(), output))
    assert app.run(config) == 130
    assert "Interrupted" in output.getvalue()

