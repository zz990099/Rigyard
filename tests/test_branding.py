import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from rigyard.cli.branding import DEFAULT_LOGO
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.config.loader import load_config
from rigyard.config.models import RigyardBranding


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def write_project(tmp_path: Path, branding: str = "") -> Path:
    (tmp_path / "containers.yaml").write_text("dev: {image: ubuntu}\n", encoding="utf-8")
    manifest = tmp_path / "rigyard.yaml"
    manifest.write_text(
        "version: 3\n"
        "metadata: {name: branding-test}\n"
        f"{branding}"
        "sources: {containers: containers.yaml}\n",
        encoding="utf-8",
    )
    return manifest


def test_menu_uses_default_logo_when_branding_is_omitted(tmp_path: Path):
    output = TTYBuffer()

    assert MenuApp(MenuIO(TTYBuffer("0\n"), output)).run(write_project(tmp_path)) == 0

    assert DEFAULT_LOGO in output.getvalue()


def test_menu_uses_custom_logo_instead_of_default(tmp_path: Path):
    output = TTYBuffer()
    config = write_project(tmp_path, "branding:\n  logo: |\n    ACME\n    ROBOTICS\n")

    assert MenuApp(MenuIO(TTYBuffer("0\n"), output)).run(config) == 0

    rendered = output.getvalue()
    assert "ACME\nROBOTICS" in rendered
    assert DEFAULT_LOGO not in rendered
    assert load_config(config).branding.logo == "ACME\nROBOTICS"


@pytest.mark.parametrize(
    "logo, message",
    [
        ("   ", "must not be empty"),
        ("line\n" * 12 + "line", "must not exceed 12 lines"),
        ("x" * 101, "must not exceed 100 display columns"),
        ("\x1b[31munsafe", "must not contain control characters"),
        ("界" * 51, "must not exceed 100 display columns"),
    ],
)
def test_branding_rejects_terminal_unsafe_or_oversized_logos(logo: str, message: str):
    with pytest.raises(ValidationError, match=message):
        RigyardBranding(logo=logo)


def test_branding_normalizes_yaml_style_trailing_newlines():
    assert RigyardBranding(logo="ACME\n").logo == "ACME"
