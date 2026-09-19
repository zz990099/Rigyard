import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from rigyard.cli.branding import DEFAULT_LOGO
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.config.loader import load_config
from rigyard.config.models import RigyardBranding, RigyardBrandingSource
from rigyard.errors import ConfigIOError, SchemaValidationError


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


def test_external_logo_supports_manifest_variables(tmp_path: Path):
    output = TTYBuffer()
    logo = tmp_path / "shared" / "logo.txt"
    logo.parent.mkdir()
    logo.write_text("VARIABLE\nLOGO\n", encoding="utf-8")
    config = write_project(
        tmp_path,
        "variables:\n"
        '  BRANDING_ROOT: "${RIGYARD_ROOT}/shared"\n'
        "branding:\n"
        '  logo_file: "${BRANDING_ROOT}/logo.txt"\n',
    )

    assert MenuApp(MenuIO(TTYBuffer("0\n"), output)).run(config) == 0
    assert load_config(config).branding.logo == "VARIABLE\nLOGO"
    assert "VARIABLE\nLOGO" in output.getvalue()


def test_external_logo_accepts_absolute_path_outside_manifest(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    logo = tmp_path / "shared-logo.txt"
    logo.write_text("SHARED", encoding="utf-8")
    config = write_project(
        project,
        f"branding:\n  logo_file: {logo.as_posix()}\n",
    )

    assert load_config(config).branding.logo == "SHARED"


def test_external_logo_resolves_plain_relative_path_from_manifest(tmp_path: Path):
    logo = tmp_path / "branding" / "logo.txt"
    logo.parent.mkdir()
    logo.write_text("RELATIVE", encoding="utf-8")
    config = write_project(tmp_path, "branding:\n  logo_file: branding/logo.txt\n")

    assert load_config(config).branding.logo == "RELATIVE"


def test_branding_rejects_inline_and_external_logo_together():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        RigyardBrandingSource(logo="INLINE", logo_file=Path("logo.txt"))


def test_external_logo_reports_missing_file(tmp_path: Path):
    config = write_project(tmp_path, "branding:\n  logo_file: missing.txt\n")

    with pytest.raises(ConfigIOError, match="missing.txt"):
        load_config(config)


def test_external_logo_uses_the_same_content_validation(tmp_path: Path):
    (tmp_path / "logo.txt").write_text("x" * 101, encoding="utf-8")
    config = write_project(tmp_path, "branding:\n  logo_file: logo.txt\n")

    with pytest.raises(SchemaValidationError, match="100 display columns"):
        load_config(config)
