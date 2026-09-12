from pathlib import Path

import pytest

from toolchain.config.loader import load_config, load_values
from toolchain.errors import ConfigIOError, SchemaValidationError


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_invalid_prompt_reports_source_location(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 1
containers:
  dev:
    image: ubuntu
    privileged:
      default: false
      prompt: {mode: select, message: Pick}
""",
    )
    with pytest.raises(SchemaValidationError) as error:
        load_config(config)
    assert str(config) in str(error.value)
    assert "options" in str(error.value)


def test_top_level_parameters_are_rejected(tmp_path: Path):
    config = write(tmp_path / "toolchain.yaml", "version: 1\nparameters: {}\n")
    with pytest.raises(SchemaValidationError, match="parameters"):
        load_config(config)


def test_invalid_yaml_and_values_shape(tmp_path: Path):
    with pytest.raises(ConfigIOError, match="invalid YAML"):
        load_config(write(tmp_path / "bad.yaml", "version: [\n"))
    with pytest.raises(SchemaValidationError, match="must contain a mapping"):
        load_values(write(tmp_path / "values.yaml", "- one\n- two\n"))
