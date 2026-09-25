from pathlib import Path

import pytest

from rigyard.config.loader import load_config, load_values
from rigyard.errors import ConfigIOError, SchemaValidationError


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def manifest(tmp_path: Path, sources: str) -> Path:
    return write(
        tmp_path / "rigyard.yaml",
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
        tmp_path / "rigyard.yaml",
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

    with pytest.raises(TypeError):
        loaded.variables["WORKSPACE_ROOT"] = "/changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.containers["other"] = loaded.containers["development"]  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.source_files["containers"][0].definitions["other"] = (  # type: ignore[index]
            loaded.containers["development"]
        )


def test_manifest_loads_multiple_sources_with_descriptions(tmp_path: Path):
    config = manifest(
        tmp_path,
        "  containers:\n    - config/a.yaml\n    - config/b.yaml",
    )
    write(tmp_path / "config/a.yaml", "description: A containers\ndev-a: {image: ubuntu}\n")
    write(tmp_path / "config/b.yaml", "description: B containers\ndev-b: {image: ubuntu}\n")

    loaded = load_config(config)

    assert list(loaded.containers) == ["dev-a", "dev-b"]
    assert [source.description for source in loaded.source_files["containers"]] == [
        "A containers",
        "B containers",
    ]
    assert [source.names for source in loaded.source_files["containers"]] == [
        ("dev-a",),
        ("dev-b",),
    ]


def test_duplicate_definitions_across_sources_are_allowed(tmp_path: Path):
    config = manifest(
        tmp_path,
        "  containers:\n    - config/a.yaml\n    - config/b.yaml",
    )
    first = write(tmp_path / "config/a.yaml", "dev: {image: ubuntu}\n")
    second = write(tmp_path / "config/b.yaml", "dev: {image: ubuntu}\n")

    loaded = load_config(config)

    assert loaded.duplicate_names["containers"]["dev"] == (
        first.resolve(),
        second.resolve(),
    )
    assert [source.names for source in loaded.source_files["containers"]] == [
        ("dev",),
        ("dev",),
    ]


@pytest.mark.parametrize(
    ("name", "content", "load"),
    [
        (
            "rigyard.yaml",
            "version: 3\nmetadata: {name: first, name: second}\nsources: {containers: x}\n",
            load_config,
        ),
        (
            "values.yaml",
            "tasks:\n  build: {container: first, container: second}\n",
            load_values,
        ),
    ],
)
def test_duplicate_yaml_keys_report_both_positions(tmp_path: Path, name, content, load):
    path = write(tmp_path / name, content)

    with pytest.raises(ConfigIOError) as error:
        load(path)

    assert "duplicate key" in str(error.value)
    assert "first defined at line" in str(error.value)
    assert str(path) in str(error.value)


def test_duplicate_key_in_definition_source_is_rejected(tmp_path: Path):
    config = manifest(tmp_path, "  containers: containers.yaml")
    write(tmp_path / "containers.yaml", "dev: {image: first}\ndev: {image: second}\n")

    with pytest.raises(ConfigIOError, match="duplicate key 'dev'"):
        load_config(config)


def test_yaml_merge_can_override_a_default(tmp_path: Path):
    path = write(
        tmp_path / "values.yaml",
        "defaults: &defaults {container: old}\nselected: {<<: *defaults, container: new}\n",
    )

    assert load_values(path)["selected"]["container"] == "new"


@pytest.mark.parametrize(
    "content",
    [
        "item: {<<: {x: 1, x: 2}}\n",
        "item: {<<: [{x: 1}, {y: 1, y: 2}]}\n",
        "item: {<<: {<<: {x: 1, x: 2}}}\n",
    ],
)
def test_duplicate_keys_in_merge_sources_are_rejected(tmp_path: Path, content):
    with pytest.raises(ConfigIOError, match="duplicate key"):
        load_values(write(tmp_path / "values.yaml", content))


def test_merged_anchor_can_be_reused_without_false_duplicates(tmp_path: Path):
    path = write(
        tmp_path / "values.yaml",
        "item: {<<: &derived {<<: {x: 1}, x: 2}}\n"
        "alias: *derived\n"
        "merged: {<<: *derived, x: 3}\n"
        "sequence: {<<: [*derived, {x: 4}]}\n",
    )

    assert load_values(path) == {
        "item": {"x": 2},
        "alias": {"x": 2},
        "merged": {"x": 3},
        "sequence": {"x": 2},
    }


def test_source_description_must_be_a_non_empty_string(tmp_path: Path):
    config = manifest(tmp_path, "  containers: config/containers.yaml")
    write(tmp_path / "config/containers.yaml", "description: []\ndev: {image: ubuntu}\n")

    with pytest.raises(SchemaValidationError, match="source description"):
        load_config(config)


def test_empty_source_list_is_rejected(tmp_path: Path):
    config = manifest(tmp_path, "  containers: []")

    with pytest.raises(SchemaValidationError, match="source list must not be empty"):
        load_config(config)


def test_manifest_rejects_invalid_global_variable_names(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
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
    config = write(tmp_path / "rigyard.yaml", "version: 1\nimages: {}\n")
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
