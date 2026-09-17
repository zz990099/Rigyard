from pathlib import Path

import pytest

from toolchain.errors import ImageBuildError
from toolchain.images.models import BuildStepResult, ImageSpec
from toolchain.images.planner import ImageBuildPlanner
from toolchain.images.service import ImageBuildService


class RecordingBackend:
    def __init__(self, fail_at=None):
        self.available = False
        self.steps = []
        self.fail_at = fail_at

    def check_available(self):
        self.available = True

    def build_step(self, step):
        self.steps.append(step)
        if step.index == self.fail_at:
            raise ImageBuildError("stopped")
        return BuildStepResult(step.index, step.layer_name, step.output_tag, ("fake",))


def setup_spec(tmp_path: Path) -> tuple[Path, ImageSpec]:
    config = tmp_path / "toolchain.yaml"
    config.write_text("version: 3\n", encoding="utf-8")
    for name in ("one", "two", "three"):
        (tmp_path / f"{name}.Dockerfile").write_text(f"RUN echo {name}\n", encoding="utf-8")
    spec = ImageSpec.model_validate(
        {
            "base": "ubuntu:22.04",
            "tag": "example/test:latest",
            "layers": [
                {"name": name, "dockerfile": f"{name}.Dockerfile"}
                for name in ("one", "two", "three")
            ],
        }
    )
    return config, spec


def test_service_builds_every_step_in_order(tmp_path: Path) -> None:
    config, spec = setup_spec(tmp_path)
    backend = RecordingBackend()
    plan = ImageBuildPlanner().create_plan("test", spec, config)
    result = ImageBuildService(backend).build(plan)
    assert backend.available
    assert [step.layer_name for step in backend.steps] == ["one", "two", "three"]
    assert result.final_tag == "example/test:latest"


def test_service_stops_at_first_failure(tmp_path: Path) -> None:
    config, spec = setup_spec(tmp_path)
    backend = RecordingBackend(fail_at=2)
    plan = ImageBuildPlanner().create_plan("test", spec, config)
    with pytest.raises(ImageBuildError, match="stopped"):
        ImageBuildService(backend).build(plan)
    assert [step.index for step in backend.steps] == [1, 2]


@pytest.mark.parametrize('fail_at', [None, 2])
def test_alias_is_only_updated_after_all_layers_succeed(tmp_path, fail_at):
    config, spec = setup_spec(tmp_path)
    spec = spec.model_copy(update={'tag_alias': 'example/test:stable'})

    class AliasBackend(RecordingBackend):
        def __init__(self):
            super().__init__(fail_at=fail_at)
            self.aliases = []

        def tag_image(self, source, alias):
            assert len(self.steps) == 3
            self.aliases.append((source, alias))

    backend = AliasBackend()
    plan = ImageBuildPlanner().create_plan('test', spec, config)
    if fail_at:
        with pytest.raises(ImageBuildError):
            ImageBuildService(backend).build(plan)
        assert backend.aliases == []
    else:
        result = ImageBuildService(backend).build(plan)
        assert backend.aliases == [('example/test:latest', 'example/test:stable')]
        assert result.tag_alias == 'example/test:stable'


def test_identical_alias_does_not_retag(tmp_path):
    config, spec = setup_spec(tmp_path)
    spec = spec.model_copy(update={'tag_alias': spec.tag})
    result = ImageBuildService(RecordingBackend()).build(
        ImageBuildPlanner().create_plan('test', spec, config)
    )
    assert result.tag_alias == spec.tag
