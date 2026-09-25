from pathlib import Path

import pytest

from rigyard.errors import ImageConfigError, ImagePlanError
from rigyard.images.models import ImageSpec
from rigyard.images.planner import ImageBuildPlanner


def make_project(tmp_path: Path) -> Path:
    config = tmp_path / "rigyard.yaml"
    config.write_text("version: 3\n")
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


def test_network_inherits_from_image_and_can_be_overridden_per_layer(tmp_path: Path):
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "tag": "example/development:latest",
            "network": "default",
            "layers": [
                {"name": "system", "dockerfile": "system.Dockerfile"},
                {"name": "app", "dockerfile": "app.Dockerfile", "network": "none"},
            ],
        }
    )
    first, second = ImageBuildPlanner().create_plan("development", spec, config).steps
    assert first.network == "default"
    assert second.network == "none"


@pytest.mark.parametrize("enabled", [True, False])
def test_build_proxy_is_applied_atomically_to_every_layer(tmp_path: Path, enabled: bool):
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "tag": "example/development:latest",
            "build_proxy": {
                "enabled": enabled,
                "network": "host",
                "build_args": {
                    "http_proxy": "http://127.0.0.1:7897",
                    "https_proxy": "http://127.0.0.1:7897",
                },
            },
            "layers": [
                {"name": "system", "dockerfile": "system.Dockerfile"},
                {"name": "app", "dockerfile": "app.Dockerfile"},
            ],
        }
    )
    steps = ImageBuildPlanner().create_plan("development", spec, config).steps
    for step in steps:
        assert step.network == ("host" if enabled else None)
        assert dict(step.build_args) == (
            {
                "http_proxy": "http://127.0.0.1:7897",
                "https_proxy": "http://127.0.0.1:7897",
            }
            if enabled
            else {}
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"network": "none"},
        {"build_args": {"HTTP_PROXY": "http://other:8080"}},
        {"layers": [{"name": "system", "dockerfile": "system.Dockerfile", "network": "none"}]},
    ],
)
def test_enabled_build_proxy_rejects_conflicting_options(tmp_path: Path, overrides: dict):
    config = make_project(tmp_path)
    data = {
        "base": "ubuntu:22.04",
        "tag": "example/development:latest",
        "build_proxy": {
            "enabled": True,
            "network": "host",
            "build_args": {"http_proxy": "http://127.0.0.1:7897"},
        },
        "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        **overrides,
    }
    with pytest.raises(ImagePlanError, match="conflict"):
        ImageBuildPlanner().create_plan("development", ImageSpec.model_validate(data), config)


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


@pytest.mark.parametrize("alias", ["", "-bad", "bad tag", "image@sha256:abc"])
def test_invalid_alias_fails_before_build(tmp_path, alias):
    config = make_project(tmp_path)
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu",
            "tag": "example:test",
            "tag_alias": alias,
            "layers": [{"name": "system", "dockerfile": "system.Dockerfile"}],
        }
    )
    with pytest.raises(ImagePlanError, match="tag_alias"):
        ImageBuildPlanner().create_plan("test", spec, config)
