from pathlib import Path

import pytest

from toolchain.errors import ConfigIOError, SchemaValidationError
from toolchain.loader import load_schema, load_values


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_schema_reports_source_location(tmp_path: Path) -> None:
    schema = write(
        tmp_path / "schema.yaml",
        "version: 1\nparameters:\n  mode:\n    type: choice\n",
    )
    with pytest.raises(SchemaValidationError) as caught:
        load_schema(schema)
    assert str(schema) in str(caught.value)
    assert ":3:" in str(caught.value) or ":4:" in str(caught.value)
    assert "options" in str(caught.value)


def test_invalid_yaml_is_io_error(tmp_path: Path) -> None:
    schema = write(tmp_path / "bad.yaml", "version: [\n")
    with pytest.raises(ConfigIOError, match="invalid YAML"):
        load_schema(schema)


def test_values_must_be_mapping(tmp_path: Path) -> None:
    values = write(tmp_path / "values.yaml", "- one\n- two\n")
    with pytest.raises(SchemaValidationError, match="must contain a mapping"):
        load_values(values)

