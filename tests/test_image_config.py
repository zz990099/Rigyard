from pathlib import Path

import pytest
from pydantic import ValidationError

from rigyard.config.loader import load_config
from rigyard.config.models import ImageDefinitions
from rigyard.parameters.models import PromptValue


def test_external_image_source_contains_inline_prompts(tmp_path: Path):
    manifest = tmp_path / "rigyard.yaml"
    manifest.write_text(
        """version: 3
metadata: {name: test-project}
sources: {images: config/images.yaml}
"""
    )
    source = tmp_path / "config/images.yaml"
    source.parent.mkdir()
    source.write_text(
        """development:
  base:
    default: ubuntu:22.04
    prompt:
      mode: select
      message: Select base
      options: [ubuntu:22.04, ubuntu:24.04]
  tag: example/development:latest
  build_args:
    MODE:
      default: release
      prompt: {mode: input, message: Build mode}
  layers:
    - name: system
      dockerfile: system.Dockerfile
"""
    )
    image = load_config(manifest).images["development"]
    assert isinstance(image.base, PromptValue)
    assert isinstance(image.build_args["MODE"], PromptValue)


@pytest.mark.parametrize(
    "image",
    [
        {"base": "ubuntu", "tag": "test", "layers": []},
        {
            "base": "ubuntu",
            "tag": "test",
            "layers": [
                {"name": "same", "dockerfile": "one"},
                {"name": "same", "dockerfile": "two"},
            ],
        },
        {
            "base": "ubuntu",
            "tag": "test",
            "build_args": {"BAD-NAME": "x"},
            "layers": [{"name": "one", "dockerfile": "one"}],
        },
        {"base": 22, "tag": "test", "layers": [{"name": "one", "dockerfile": "one"}]},
    ],
)
def test_invalid_image_templates_are_rejected(image):
    with pytest.raises(ValidationError):
        ImageDefinitions.model_validate({"test": image})


def test_invalid_image_name_is_rejected():
    with pytest.raises(ValidationError, match="invalid image name"):
        ImageDefinitions.model_validate(
            {
                "bad name": {
                    "base": "ubuntu",
                    "tag": "test",
                    "layers": [{"name": "one", "dockerfile": "one"}],
                }
            }
        )
