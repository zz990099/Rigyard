from pathlib import Path

import pytest
from pydantic import ValidationError

from toolchain.config.loader import load_config
from toolchain.config.models import ToolchainConfig
from toolchain.parameters.models import PromptValue


def test_project_config_contains_inline_image_prompts(tmp_path: Path):
    path = tmp_path / "toolchain.yaml"
    path.write_text("""version: 1
images:
  development:
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
""")
    image = load_config(path).images["development"]
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
        ToolchainConfig.model_validate({"version": 1, "images": {"test": image}})
