from pathlib import Path

import pytest

from rigyard.application.parameters import InspectParametersUseCase, ResolveParametersUseCase
from rigyard.application.requests import ResolutionRequest
from rigyard.config.catalog import DefinitionCatalog
from rigyard.config.loader import load_config
from rigyard.errors import SchemaValidationError


def project(tmp_path: Path) -> Path:
    manifest = tmp_path / "rigyard.yaml"
    manifest.write_text("version: 3\nmetadata: {name: demo}\nsources: {tasks: [a.yaml, b.yaml]}\n")
    for name in ("a", "b"):
        (tmp_path / f"{name}.yaml").write_text(
            "run:\n  container:\n    default: " + name + "\n"
            "    prompt: {mode: input, message: Container}\n  script: /run.sh\n"
        )
    return manifest


def test_catalog_preserves_source_identity_and_rejects_ambiguity(tmp_path: Path):
    manifest = project(tmp_path)
    catalog = DefinitionCatalog(load_config(manifest), manifest)
    assert len(catalog.entries) == 2
    with pytest.raises(SchemaValidationError, match="ambiguous"):
        catalog.find("tasks", "run")
    assert catalog.find("tasks", "run", Path("b.yaml")).source_path == tmp_path / "b.yaml"
    assert catalog.find("tasks", "missing") is None
    with pytest.raises(SchemaValidationError, match="unknown tasks source"):
        catalog.find("tasks", "run", Path("missing.yaml"))
    with pytest.raises(SchemaValidationError, match="unknown task"):
        catalog.find("tasks", "missing", Path("b.yaml"))


def test_inspect_and_resolve_do_not_silently_pick_first_duplicate(tmp_path: Path):
    manifest = project(tmp_path)
    with pytest.raises(SchemaValidationError, match="ambiguous"):
        InspectParametersUseCase().execute(manifest)
    with pytest.raises(SchemaValidationError, match="ambiguous"):
        ResolveParametersUseCase().execute(ResolutionRequest(manifest, interactive=False))
    assert (
        "tasks.run.container"
        in InspectParametersUseCase().execute(manifest, Path("b.yaml"))["runtime_values"]
    )
    context = ResolveParametersUseCase().execute(
        ResolutionRequest(manifest, interactive=False, source_path=Path("b.yaml"))
    )
    assert context["tasks.run.container"] == "b"
    with pytest.raises(SchemaValidationError, match="unknown configuration source"):
        InspectParametersUseCase().execute(manifest, Path("missing.yaml"))
