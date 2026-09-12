from pathlib import Path

import pytest

from toolchain.errors import ImageConfigError, ImagePlanError
from toolchain.images.models import ImageSpec
from toolchain.images.planner import ImageBuildPlanner
from toolchain.parameters.context import ResolvedContext, ResolvedValue, ValueSource


def resolved(**values) -> ResolvedContext:
    return ResolvedContext(
        {name: ResolvedValue(value, ValueSource.DEFAULT) for name, value in values.items()}
    )


def make_project(tmp_path: Path) -> Path:
    config = tmp_path / "toolchain.yaml"
    config.write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "system.Dockerfile").write_text("RUN echo system\n", encoding="utf-8")
    (tmp_path / "ros.Dockerfile").write_text("ARG ROS_DISTRO\nRUN echo ok\n", encoding="utf-8")
    return config


def test_plan_chains_layers_and_resolves_build_args(tmp_path: Path) -> None:
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": {"parameter": "base_image"},
            "context": ".",
            "tag": "example/development:latest",
            "build_args": {"ROS_DISTRO": {"parameter": "ros_distro"}, "MODE": "debug"},
            "layers": [
                {"name": "system", "dockerfile": "system.Dockerfile"},
                {
                    "name": "ros",
                    "dockerfile": "ros.Dockerfile",
                    "build_args": {"MODE": "release"},
                },
            ],
        }
    )
    plan = ImageBuildPlanner().create_plan(
        "development",
        spec,
        resolved(base_image="ubuntu:22.04", ros_distro="humble"),
        config,
    )
    first, second = plan.steps
    assert first.base_image == "ubuntu:22.04"
    assert first.output_tag.startswith("toolchain.local/")
    assert second.base_image == first.output_tag
    assert second.output_tag == "example/development:latest"
    assert dict(second.build_args) == {"MODE": "release", "ROS_DISTRO": "humble"}
    with pytest.raises(TypeError):
        second.build_args["MODE"] = "changed"


def test_missing_parameter_reference_is_actionable(tmp_path: Path) -> None:
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": {"parameter": "missing"},
            "tag": "example/test:latest",
            "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        }
    )
    with pytest.raises(ImagePlanError, match="unresolved or disabled parameter 'missing'"):
        ImageBuildPlanner().create_plan("test", spec, resolved(), config)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("FROM ubuntu:22.04\nRUN true\n", "cannot contain FROM"),
        ("# syntax=docker/dockerfile:1\nRUN true\n", "parser directives"),
        ("\n", "must not be empty"),
    ],
)
def test_invalid_fragments_are_rejected(tmp_path: Path, content: str, message: str) -> None:
    config = make_project(tmp_path)
    (tmp_path / "system.Dockerfile").write_text(content, encoding="utf-8")
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "tag": "example/test:latest",
            "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        }
    )
    with pytest.raises(ImageConfigError, match=message):
        ImageBuildPlanner().create_plan("test", spec, resolved(), config)


def test_invalid_context_is_rejected_before_build(tmp_path: Path) -> None:
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "context": "missing",
            "tag": "example/test:latest",
            "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        }
    )
    with pytest.raises(ImageConfigError, match="context is not a directory"):
        ImageBuildPlanner().create_plan("test", spec, resolved(), config)

