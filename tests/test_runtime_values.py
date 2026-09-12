from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from toolchain.config.models import ToolchainConfig
from toolchain.containers.models import ContainerSpec
from toolchain.errors import MissingValueError, ResolutionError
from toolchain.parameters.models import PromptValue
from toolchain.parameters.resolver import (
    RuntimeValueResolver,
    collect_prompts,
    environment_name,
    materialize_as,
)


def prompt(mode="input", default="value", **prompt_options):
    data = {"prompt": {"mode": mode, "message": "Choose", **prompt_options}}
    if default is not _MISSING:
        data["default"] = default
    return PromptValue.model_validate(data)


_MISSING = object()


def test_prompt_schema_validates_modes_and_defaults():
    assert prompt("confirm", False).default is False
    assert prompt("select", "a", options=["a", "b"]).prompt.options == ("a", "b")
    assert prompt("input", ["a"], repeat=True).prompt.repeat
    for data in (
        {"default": "no", "prompt": {"mode": "confirm", "message": "x"}},
        {"default": "x", "prompt": {"mode": "select", "message": "x", "options": ["a"]}},
        {"default": [], "prompt": {"mode": "confirm", "message": "x", "repeat": True}},
    ):
        with pytest.raises(ValidationError):
            PromptValue.model_validate(data)


def test_prompts_are_discovered_by_configuration_path():
    config = ToolchainConfig.model_validate(
        {
            "version": 2,
            "metadata": {"name": "test"},
            "sources": {"containers": "containers.yaml"},
            "containers": {
                "development": {
                    "image": "ubuntu",
                    "privileged": {
                        "default": False,
                        "prompt": {"mode": "confirm", "message": "Privileged?"},
                    },
                    "mounts": {
                        "default": ["./:/workspace"],
                        "prompt": {"mode": "input", "message": "Mount", "repeat": True},
                    },
                }
            },
        }
    )
    assert list(collect_prompts(config)) == [
        "containers.development.privileged",
        "containers.development.mounts",
    ]


def test_interactive_prompt_runs_with_default_and_noninteractive_uses_default():
    values = {"x": prompt("confirm", False)}
    resolver = RuntimeValueResolver(values)
    assert resolver.resolve(interactive=False)["x"] is False
    assert resolver.resolve(input_fn=lambda _: "y")["x"] is True


def test_nested_values_environment_and_override_precedence():
    resolver = RuntimeValueResolver({"containers.dev.name": prompt()})
    env = {environment_name("containers.dev.name"): "environment"}
    context = resolver.resolve(
        values={"containers": {"dev": {"name": "values"}}},
        environ=env,
        overrides={"containers.dev.name": "override"},
        interactive=False,
    )
    assert context["containers.dev.name"] == "override"
    assert context.resolved("containers.dev.name").source.value == "cli"


def test_explicit_sources_are_normalized_by_interaction_mode():
    resolver = RuntimeValueResolver(
        {
            "confirm": prompt("confirm", False),
            "select": prompt("select", 1, options=[1, 2]),
            "repeat": prompt("input", [], repeat=True),
        }
    )
    context = resolver.resolve(
        values={"confirm": "yes", "select": "2", "repeat": ["a", "b"]},
        interactive=False,
    )
    assert context.as_dict() == {"confirm": True, "select": 2, "repeat": ["a", "b"]}
    with pytest.raises(ResolutionError, match="invalid confirm"):
        resolver.resolve(values={"confirm": "perhaps"}, interactive=False)
    with pytest.raises(ResolutionError, match="invalid select"):
        resolver.resolve(values={"select": "3"}, interactive=False)
    with pytest.raises(ResolutionError, match="expected a list"):
        resolver.resolve(values={"repeat": "a"}, interactive=False)


def test_missing_and_unknown_values_are_actionable():
    resolver = RuntimeValueResolver({"required": prompt(default=_MISSING)})
    with pytest.raises(MissingValueError, match="required"):
        resolver.resolve(interactive=False)
    with pytest.raises(ResolutionError, match="unknown"):
        resolver.resolve(overrides={"typo": 1}, interactive=False)


def test_input_select_confirm_and_repeated_input():
    answers = iter(["", "2", "yes", "/a:/a", "/b:/b:ro", ""])
    resolver = RuntimeValueResolver(
        {
            "input": prompt(default="default"),
            "select": prompt("select", "a", options=["a", "b"]),
            "confirm": prompt("confirm", False),
            "repeat": prompt("input", [], repeat=True, item_hint="SOURCE:TARGET[:ro]"),
        }
    )
    context = resolver.resolve(input_fn=lambda _: next(answers))
    assert context.as_dict() == {
        "input": "default",
        "select": "b",
        "confirm": True,
        "repeat": ["/a:/a", "/b:/b:ro"],
    }
    with pytest.raises(FrozenInstanceError):
        context.resolved("input").value = "changed"


def test_target_model_performs_type_validation_after_interaction():
    template = ToolchainConfig.model_validate(
        {
            "version": 2,
            "metadata": {"name": "test"},
            "sources": {"containers": "containers.yaml"},
            "containers": {
                "dev": {
                    "image": "ubuntu",
                    "name": {
                        "default": False,
                        "prompt": {"mode": "confirm", "message": "Use a name?"},
                    },
                }
            },
        }
    ).containers["dev"]
    context = RuntimeValueResolver(collect_prompts(template, "containers.dev")).resolve(
        interactive=False
    )
    with pytest.raises(ResolutionError, match="containers.dev.name"):
        materialize_as(template, "containers.dev", context, ContainerSpec)
