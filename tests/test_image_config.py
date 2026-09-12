from pathlib import Path

import pytest
from pydantic import ValidationError

from toolchain.config.loader import load_config, load_schema
from toolchain.config.models import ToolchainConfig
from toolchain.images.models import ParameterRef


def test_project_config_composes_parameters_and_images(tmp_path: Path) -> None:
    config_file = tmp_path / "toolchain.yaml"
    config_file.write_text(
        """\
version: 1
parameters:
  distro:
    default: humble
images:
  development:
    base: ubuntu:22.04
    tag: example/development:latest
    build_args:
      ROS_DISTRO:
        parameter: distro
    layers:
      - name: system
        dockerfile: system.Dockerfile
""",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert isinstance(config.images["development"].build_args["ROS_DISTRO"], ParameterRef)
    assert load_schema(config_file).parameters["distro"].default == "humble"


def test_empty_parameter_section_is_supported() -> None:
    config = ToolchainConfig.model_validate(
        {
            "version": 1,
            "images": {
                "minimal": {
                    "base": "scratch",
                    "tag": "example/minimal:latest",
                    "layers": [{"name": "files", "dockerfile": "files.Dockerfile"}],
                }
            },
        }
    )
    assert config.parameters == {}


@pytest.mark.parametrize(
    "image",
    [
        {
            "base": "ubuntu:22.04",
            "tag": "example/test:latest",
            "layers": [],
        },
        {
            "base": "ubuntu:22.04",
            "tag": "example/test:latest",
            "layers": [
                {"name": "same", "dockerfile": "one"},
                {"name": "same", "dockerfile": "two"},
            ],
        },
        {
            "base": "ubuntu:22.04",
            "tag": "example/test:latest",
            "build_args": {"BAD-NAME": "value"},
            "layers": [{"name": "one", "dockerfile": "one"}],
        },
        {
            "base": 22,
            "tag": "example/test:latest",
            "layers": [{"name": "one", "dockerfile": "one"}],
        },
    ],
)
def test_invalid_image_definitions_are_rejected(image) -> None:
    with pytest.raises(ValidationError):
        ToolchainConfig.model_validate(
            {"version": 1, "parameters": {}, "images": {"test": image}}
        )
