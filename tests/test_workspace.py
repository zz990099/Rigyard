from pathlib import Path

import yaml

from toolchain.cli.main import run
from toolchain.workspace import initialize_workspace, resolve_config_path


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def project(root: Path, name: str = "workspace-test") -> Path:
    manifest = write(
        root / "toolchain.yaml",
        f"""version: 2
metadata: {{name: {name}}}
sources: {{images: images.yaml}}
""",
    )
    write(root / "images.yaml", "{}\n")
    return manifest


def test_init_records_relative_manifest_and_bare_command_uses_it(
    tmp_path: Path, monkeypatch, capsys
):
    workspace = tmp_path / "ros2_ws"
    manifest = project(workspace / "src/xbot/.toolchain")
    workspace.mkdir(exist_ok=True)
    monkeypatch.chdir(workspace)

    assert run(["init", "-f", "src/xbot/.toolchain/toolchain.yaml"]) == 0
    marker = workspace / ".toolchain/context.yaml"
    assert yaml.safe_load(marker.read_text()) == {
        "version": 1,
        "config": "src/xbot/.toolchain/toolchain.yaml",
    }
    assert resolve_config_path(None) == manifest.resolve()
    assert run(["validate"]) == 0
    assert f"OK: {manifest.resolve()}" in capsys.readouterr().out


def test_config_resolution_does_not_search_parent_directories(tmp_path: Path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    manifest = project(workspace / "config")
    child = workspace / "src"
    child.mkdir(parents=True)
    initialize_workspace(manifest, root=workspace)

    monkeypatch.chdir(child)
    assert resolve_config_path(None) == child / "toolchain.yaml"
    assert run(["validate"]) == 2
    assert str(child / "toolchain.yaml") in capsys.readouterr().err


def test_explicit_config_overrides_workspace_binding(tmp_path: Path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    configured = project(workspace / "configured", "configured")
    explicit = project(workspace / "explicit", "explicit")
    workspace.mkdir(exist_ok=True)
    initialize_workspace(configured, root=workspace)
    monkeypatch.chdir(workspace)

    assert run(["--config", str(explicit), "validate"]) == 0
    assert f"OK: {explicit.resolve()}" in capsys.readouterr().out


def test_reinitialization_is_idempotent_and_requires_force_for_change(
    tmp_path: Path, monkeypatch, capsys
):
    workspace = tmp_path / "workspace"
    first = project(workspace / "first", "first")
    second = project(workspace / "second", "second")
    workspace.mkdir(exist_ok=True)
    monkeypatch.chdir(workspace)

    assert run(["init", "-f", str(first)]) == 0
    assert run(["init", "-f", str(first)]) == 0
    assert "Already initialized" in capsys.readouterr().out

    assert run(["init", "-f", str(second)]) == 2
    assert "use --force" in capsys.readouterr().err
    assert resolve_config_path(None) == first.resolve()

    assert run(["init", "-f", str(second), "--force"]) == 0
    assert resolve_config_path(None) == second.resolve()


def test_external_manifest_is_stored_as_absolute_path(tmp_path: Path):
    workspace = tmp_path / "workspace"
    manifest = project(tmp_path / "shared-config")
    workspace.mkdir()

    result = initialize_workspace(manifest, root=workspace)

    assert result.stored_path == manifest.resolve()
    assert yaml.safe_load((workspace / ".toolchain/context.yaml").read_text())["config"] == str(
        manifest.resolve()
    )
