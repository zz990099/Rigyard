import json
from pathlib import Path

import pytest

from rigyard.application.requests import ResolutionRequest
from rigyard.config.loader import load_config
from rigyard.parameters.models import PromptValue
from rigyard.parameters.resolver import RuntimeValueResolver
from rigyard.scenarios.models import ScenarioTemplate


def test_nested_scenario_collections_cannot_be_mutated_or_changed_through_input():
    data = {
        "instances": {
            "robot": {
                "container": "dev",
                "groups": {"run": {"command": ["echo", "hello"], "environment": {"MODE": "dev"}}},
            }
        },
        "profiles": {"dev": {}},
    }
    model = ScenarioTemplate.model_validate(data)
    data["instances"]["robot"]["groups"]["run"]["environment"]["MODE"] = "changed"
    group = model.instances["robot"].groups["run"]
    assert group.environment["MODE"] == "dev"
    for mapping, key in (
        (model.instances, "robot"),
        (model.profiles, "dev"),
        (model.instances["robot"].groups, "run"),
        (group.environment, "MODE"),
    ):
        with pytest.raises(TypeError):
            mapping[key] = None
    serialized = model.model_dump(mode="json", exclude_unset=True)
    serialized["instances"]["robot"]["groups"]["run"]["environment"]["MODE"] = "outside"
    assert group.environment["MODE"] == "dev"
    restored = ScenarioTemplate.model_validate_json(model.model_dump_json(exclude_unset=True))
    assert restored == model


def test_prompt_defaults_and_overrides_are_deeply_frozen_but_resolve_to_plain_values():
    default = [{"name": "first"}]
    prompt = PromptValue.model_validate(
        {"default": default, "prompt": {"mode": "input", "message": "Choose", "repeat": True}}
    )
    default[0]["name"] = "mutated"
    assert prompt.default[0]["name"] == "first"
    with pytest.raises(TypeError):
        prompt.default[0]["name"] = "mutated"
    values = {"tasks.run.arguments": ["a", "b"]}
    request = ResolutionRequest(Path("rigyard.yaml"), overrides=values)
    values["tasks.run.arguments"].append("c")
    assert request.overrides["tasks.run.arguments"] == ("a", "b")
    resolved = RuntimeValueResolver({"x": prompt}).resolve(interactive=False)
    assert resolved["x"] == [{"name": "first"}]
    assert json.loads(json.dumps(prompt.model_dump(mode="json")))["default"] == [{"name": "first"}]


def test_source_catalog_and_resource_view_share_an_immutable_definition(tmp_path: Path):
    manifest = tmp_path / "rigyard.yaml"
    manifest.write_text("version: 3\nmetadata: {name: demo}\nsources: {containers: c.yaml}\n")
    (tmp_path / "c.yaml").write_text("dev: {image: ubuntu, environment: {MODE: dev}}\n")
    config = load_config(manifest)
    definition = config.source_files["containers"][0].definitions["dev"]
    assert definition is config.containers["dev"]
    with pytest.raises(TypeError):
        definition.environment["MODE"] = "changed"
    assert config.containers["dev"].environment["MODE"] == "dev"


def test_complex_select_options_keep_external_serialization_and_override_semantics():
    prompt = PromptValue.model_validate(
        {
            "default": ["a"],
            "prompt": {"mode": "select", "message": "Choose", "options": [["a"], ["b"]]},
        }
    )
    resolver = RuntimeValueResolver({"x": prompt})
    assert json.loads(json.dumps(resolver.inspect()))["x"]["options"] == [["a"], ["b"]]
    assert resolver.resolve(overrides={"x": ["b"]}, interactive=False)["x"] == ["b"]
