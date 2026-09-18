import io

from toolchain.cli.main import run
from toolchain.cli.style import ColorMode, Style


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_plain_style_returns_text_unchanged():
    style = Style.plain()

    assert style.enabled is False
    assert style.render("error", "boom") == "boom"
    assert style.line("Build: native") == "Build: native"


def test_enabled_style_wraps_roles():
    style = Style(enabled=True)

    assert style.render("error", "boom") == "\x1b[1;31mboom\x1b[0m"
    assert style.render("muted", "") == ""
    assert style.render("unknown", "text") == "text"
    assert style.line("Build: native") == "\x1b[2mBuild\x1b[0m: \x1b[1mnative\x1b[0m"
    assert style.line("no separator") == "no separator"


def test_for_stream_detects_terminals_and_honours_overrides():
    assert Style.for_stream(TTYBuffer(), environ={}).enabled is True
    assert Style.for_stream(io.StringIO(), environ={}).enabled is False
    assert Style.for_stream(TTYBuffer(), environ={"NO_COLOR": "1"}).enabled is False
    assert Style.for_stream(TTYBuffer(), environ={"TERM": "dumb"}).enabled is False
    assert Style.for_stream(io.StringIO(), mode=ColorMode.ALWAYS).enabled is True
    assert Style.for_stream(TTYBuffer(), mode="never").enabled is False


def test_cli_colour_option_overrides_the_stream(tmp_path, monkeypatch, capsys):
    config = tmp_path / "toolchain.yaml"
    config.write_text(
        "version: 3\nmetadata: {name: style-test}\n"
        "sources: {containers: containers.yaml}\n"
    )
    (tmp_path / "containers.yaml").write_text("dev: {image: ubuntu}\n")

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert run(["--config", str(config), "--color", "always", "validate"]) == 0
    assert "\x1b[" in capsys.readouterr().out

    assert run(["--config", str(config), "--color", "never", "validate"]) == 0
    assert "\x1b[" not in capsys.readouterr().out

    monkeypatch.setenv("NO_COLOR", "1")
    assert run(["--config", str(config), "validate"]) == 0
    assert "\x1b[" not in capsys.readouterr().out
