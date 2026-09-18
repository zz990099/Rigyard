from pathlib import Path

import pytest

from toolchain.config.loader import load_config, load_values
from toolchain.errors import ConfigIOError, SchemaValidationError


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def manifest(tmp_path: Path, sources: str) -> Path:
    return write(
        tmp_path / "toolchain.yaml",
        f"""version: 3
metadata:
  name: test-project
sources:
{sources}
""",
    )


def test_manifest_loads_relative_sources(tmp_path: Path, monkeypatch):
    config = manifest(
        tmp_path,
        "  images: config/images.yaml\n  containers: config/containers.yaml",
    )
    write(
        tmp_path / "config/images.yaml",
        """development:
  base: ubuntu
  tag: example/development
  layers: [{name: base, dockerfile: Dockerfile}]
""",
    )
    write(tmp_path / "config/containers.yaml", "development: {image: ubuntu}\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    loaded = load_config(config)
    assert loaded.metadata.name == "test-project"
    assert list(loaded.images) == ["development"]
    assert list(loaded.containers) == ["development"]


def test_manifest_loads_global_variables(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 3
metadata: {name: test-project}
variables:
  WORKSPACE_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: /workspace/project
sources: {containers: containers.yaml}
""",
    )
    write(tmp_path / "containers.yaml", "development: {image: ubuntu}\n")

    loaded = load_config(config)

    assert loaded.variables == {
        "WORKSPACE_ROOT": "/workspace",
        "CONTAINER_PROJECT_ROOT": "/workspace/project",
    }


def test_manifest_rejects_invalid_global_variable_names(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 3
metadata: {name: test-project}
variables: {bad-name: /workspace}
sources: {containers: containers.yaml}
""",
    )
    write(tmp_path / "containers.yaml", "development: {image: ubuntu}\n")

    with pytest.raises(SchemaValidationError, match="invalid global variable name"):
        load_config(config)


def test_invalid_external_prompt_reports_source_location(tmp_path: Path):
    config = manifest(tmp_path, "  containers: config/containers.yaml")
    source = write(
        tmp_path / "config/containers.yaml",
        """dev:
  image: ubuntu
  privileged:
    default: false
    prompt: {mode: select, message: Pick}
""",
    )
    with pytest.raises(SchemaValidationError) as error:
        load_config(config)
    assert str(source.resolve()) in str(error.value)
    assert "options" in str(error.value)


def test_v1_inline_configuration_is_rejected(tmp_path: Path):
    config = write(tmp_path / "toolchain.yaml", "version: 1\nimages: {}\n")
    with pytest.raises(SchemaValidationError, match="version"):
        load_config(config)


def test_manifest_requires_metadata_and_at_least_one_source(tmp_path: Path):
    with pytest.raises(SchemaValidationError, match="metadata"):
        load_config(write(tmp_path / "missing-meta.yaml", "version: 3\nsources: {images: x}\n"))
    with pytest.raises(SchemaValidationError, match="configuration source"):
        load_config(
            write(
                tmp_path / "missing-source.yaml",
                "version: 3\nmetadata: {name: test}\nsources: {}\n",
            )
        )


def test_missing_source_and_invalid_yaml_are_actionable(tmp_path: Path):
    config = manifest(tmp_path, "  images: missing.yaml")
    with pytest.raises(ConfigIOError, match="missing.yaml"):
        load_config(config)
    with pytest.raises(ConfigIOError, match="invalid YAML"):
        load_config(write(tmp_path / "bad.yaml", "version: [\n"))


def test_values_must_be_a_mapping(tmp_path: Path):
    with pytest.raises(SchemaValidationError, match="must contain a mapping"):
        load_values(write(tmp_path / "values.yaml", "- one\n- two\n"))
