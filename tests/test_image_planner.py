from pathlib import Path

import pytest

from toolchain.errors import ImageConfigError, ImagePlanError
from toolchain.images.models import ImageSpec
from toolchain.images.planner import ImageBuildPlanner


def make_project(tmp_path: Path) -> Path:
    config = tmp_path / "toolchain.yaml"
    config.write_text("version: 1\n")
    (tmp_path / "system.Dockerfile").write_text("RUN echo system\n")
    (tmp_path / "app.Dockerfile").write_text("ARG MODE\nRUN echo ok\n")
    return config


def test_plan_chains_layers_and_stringifies_build_args(tmp_path: Path):
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "tag": "example/development:latest",
            "build_args": {"MODE": "debug", "ENABLED": True},
            "layers": [
                {"name": "system", "dockerfile": "system.Dockerfile"},
                {"name": "app", "dockerfile": "app.Dockerfile", "build_args": {"MODE": "release"}},
            ],
        }
    )
    plan = ImageBuildPlanner().create_plan("development", spec, config)
    first, second = plan.steps
    assert first.base_image == "ubuntu:22.04"
    assert second.base_image == first.output_tag
    assert second.output_tag == "example/development:latest"
    assert dict(second.build_args) == {"ENABLED": "true", "MODE": "release"}
    with pytest.raises(TypeError):
        second.build_args["MODE"] = "changed"


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ("bad base", "base"),
        ("bad tag", "tag"),
    ],
)
def test_invalid_references_are_rejected(tmp_path: Path, value: str, field: str):
    config = make_project(tmp_path)
    data = {
        "base": "ubuntu",
        "tag": "example:test",
        "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
    }
    data[field] = value
    with pytest.raises(ImagePlanError):
        ImageBuildPlanner().create_plan("test", ImageSpec.model_validate(data), config)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("FROM ubuntu\n", "cannot contain FROM"),
        ("# syntax=docker/dockerfile:1\nRUN true\n", "parser directives"),
        ("\n", "must not be empty"),
    ],
)
def test_invalid_fragments_are_rejected(tmp_path: Path, content: str, message: str):
    config = make_project(tmp_path)
    (tmp_path / "system.Dockerfile").write_text(content)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu",
            "tag": "test:latest",
            "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        }
    )
    with pytest.raises(ImageConfigError, match=message):
        ImageBuildPlanner().create_plan("test", spec, config)
