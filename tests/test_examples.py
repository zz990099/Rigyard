from pathlib import Path

import pytest

from rigyard.application.parameters import ValidateConfigUseCase

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["minimal", "robot-development"])
def test_repository_example_is_valid(name: str):
    config = ValidateConfigUseCase().execute(ROOT / "examples" / name / "rigyard.yaml")

    assert config.metadata.name


def test_full_example_exercises_manifest_defaults_and_all_source_kinds():
    config = ValidateConfigUseCase().execute(
        ROOT / "examples" / "robot-development" / "rigyard.yaml"
    )

    assert config.workspace.command_alias == "robot"
    assert "ROBOT DEVELOPMENT" in (config.branding.logo or "")
    assert all(
        config.source_files[kind]
        for kind in ("images", "containers", "builds", "tests", "tasks", "scenarios")
    )
