from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from rigyard.config.models import RigyardConfig
from rigyard.containers.models import ContainerSpec
from rigyard.errors import MissingValueError, ResolutionError
from rigyard.parameters.models import PromptValue
from rigyard.parameters.resolver import (
    RuntimeValueResolver,
    collect_prompts,
    environment_name,
    materialize_as,
)
from rigyard.parameters.sources import DynamicOption, PromptSource


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


def test_input_composition_schema_is_explicit_and_rejects_ambiguous_forms():
    appended = PromptValue.model_validate(
        {
            "base": ["fixed"],
            "default": "host",
            "prompt": {
                "mode": "input",
                "message": "Path",
                "merge": "append",
                "input_template": "${INPUT}:/target",
            },
        }
    )
    assert appended.base == ["fixed"]
    assert appended.prompt.merge.value == "append"

    invalid = (
        {
            "default": "host",
            "prompt": {"mode": "input", "message": "x", "merge": "append"},
        },
        {
            "base": "fixed",
            "prompt": {"mode": "input", "message": "x", "merge": "append"},
        },
        {
            "base": ["fixed"],
            "prompt": {"mode": "input", "message": "x"},
        },
        {
            "prompt": {"mode": "input", "message": "x", "input_template": "no marker"},
        },
        {
            "prompt": {
                "mode": "input",
                "message": "x",
                "input_template": "${INPUT}-${INPUT}",
            },
        },
        {
            "prompt": {
                "mode": "select",
                "message": "x",
                "options": ["a"],
                "input_template": "${INPUT}",
            },
        },
    )
    for data in invalid:
        with pytest.raises(ValidationError):
            PromptValue.model_validate(data)


def test_prompts_are_discovered_by_configuration_path():
    config = RigyardConfig.model_validate(
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


def test_input_template_applies_to_default_interactive_and_explicit_sources():
    configured = PromptValue.model_validate(
        {
            "default": "default",
            "prompt": {
                "mode": "input",
                "message": "Name",
                "input_template": "${INPUT}_dev",
            },
        }
    )
    resolver = RuntimeValueResolver({"name": configured})

    assert resolver.resolve(interactive=False)["name"] == "default_dev"
    assert resolver.resolve(input_fn=lambda _: "interactive")["name"] == "interactive_dev"
    assert resolver.resolve(values={"name": "values"}, interactive=False)["name"] == "values_dev"
    assert resolver.resolve(
        environ={environment_name("name"): "environment"}, interactive=False
    )["name"] == "environment_dev"
    assert resolver.resolve(overrides={"name": "cli"}, interactive=False)["name"] == "cli_dev"


def test_append_preserves_base_and_templates_scalar_or_repeated_input():
    scalar = PromptValue.model_validate(
        {
            "base": ["fixed:/workspace"],
            "default": "~/sysroot",
            "prompt": {
                "mode": "input",
                "message": "Sysroot",
                "merge": "append",
                "input_template": "${INPUT}:/opt/sysroot",
            },
        }
    )
    repeated = PromptValue.model_validate(
        {
            "base": ["fixed"],
            "default": ["one"],
            "prompt": {
                "mode": "input",
                "message": "Item",
                "repeat": True,
                "merge": "append",
                "input_template": "prefix-${INPUT}",
            },
        }
    )

    assert RuntimeValueResolver({"mounts": scalar}).resolve(interactive=False)["mounts"] == [
        "fixed:/workspace",
        "~/sysroot:/opt/sysroot",
    ]
    assert RuntimeValueResolver({"items": repeated}).resolve(
        values={"items": ["two", "three"]}, interactive=False
    )["items"] == ["fixed", "prefix-two", "prefix-three"]


def test_input_template_rejects_mapping_values():
    configured = PromptValue.model_validate(
        {
            "prompt": {
                "mode": "input",
                "message": "Value",
                "input_template": "${INPUT}-suffix",
            }
        }
    )

    with pytest.raises(ResolutionError, match="expected a scalar or list"):
        RuntimeValueResolver({"value": configured}).resolve(
            overrides={"value": {"nested": True}}, interactive=False
        )


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


def test_prompt_default_hint_is_rendered_for_display():
    seen: list[str] = []
    resolver = RuntimeValueResolver(
        {"dev": prompt(default="dev_${env:USER}")},
        render_default=lambda path, value: value.replace("${env:USER}", "root"),
    )

    context = resolver.resolve(input_fn=lambda text: seen.append(text) or "")

    assert seen == ["Choose [dev_root]: "]
    # The hint is rendered, the accepted default stays raw and is rendered once more
    # together with the rest of the selected definition.
    assert context["dev"] == "dev_${env:USER}"


def test_prompt_default_hint_falls_back_when_rendering_fails():
    def broken(path: str, value: str) -> str:
        raise ResolutionError("missing environment variable 'USER'")

    seen: list[str] = []
    resolver = RuntimeValueResolver(
        {"dev": prompt(default="dev_${env:USER}")},
        render_default=broken,
    )

    context = resolver.resolve(input_fn=lambda text: seen.append(text) or "")

    assert seen == ["Choose [dev_${env:USER}]: "]
    assert context["dev"] == "dev_${env:USER}"


def dynamic_prompt(**source_options) -> PromptValue:
    return PromptValue.model_validate(
        {
            "default": "dev",
            "prompt": {
                "mode": "select",
                "message": "Container",
                "source": {"provider": "containers", **source_options},
            },
        }
    )


def recording_provider(options):
    calls = []

    def provide(source):
        calls.append(source)
        return options

    return provide, calls


def test_select_prompt_with_source_uses_dynamic_candidates():
    provider, calls = recording_provider(
        (DynamicOption("dev", "running"), DynamicOption("dev-2", "exited"))
    )
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt(filter="^dev")},
        sources={"containers": provider},
    )
    seen: list[str] = []

    context = resolver.resolve(input_fn=lambda text: seen.append(text) or "2")

    assert seen == ["  1) dev    running\n  2) dev-2  exited\nContainer [dev]: "]
    assert context["containers.dev.name"] == "dev-2"
    assert len(calls) == 1
    assert calls[0] == PromptSource(provider="containers", filter="^dev")


def test_dynamic_source_accepts_a_name_outside_the_candidate_list():
    provider, _ = recording_provider((DynamicOption("dev"),))
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt()}, sources={"containers": provider}
    )

    context = resolver.resolve(input_fn=lambda _: "some-other-container")

    assert context["containers.dev.name"] == "some-other-container"


def test_dynamic_source_returns_the_default_on_an_empty_answer():
    provider, _ = recording_provider(())
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt()}, sources={"containers": provider}
    )
    seen: list[str] = []

    context = resolver.resolve(input_fn=lambda text: seen.append(text) or "")

    assert seen == ["Container [dev]: "]  # No empty candidate block is shown.
    assert context["containers.dev.name"] == "dev"


def test_dynamic_source_is_not_queried_without_interaction():
    provider, calls = recording_provider((DynamicOption("dev"),))
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt()}, sources={"containers": provider}
    )

    assert resolver.resolve(interactive=False)["containers.dev.name"] == "dev"
    assert resolver.resolve(values={"containers": {"dev": {"name": "from-values"}}},
                            interactive=False)["containers.dev.name"] == "from-values"
    assert resolver.resolve(overrides={"containers.dev.name": "from-cli"},
                            interactive=False)["containers.dev.name"] == "from-cli"
    assert calls == []


def test_dynamic_source_is_looked_up_once_per_source_specification():
    provider, calls = recording_provider((DynamicOption("dev"),))
    resolver = RuntimeValueResolver(
        {
            "containers.a.name": dynamic_prompt(filter="^dev"),
            "containers.b.name": dynamic_prompt(filter="^dev"),
        },
        sources={"containers": provider},
    )

    resolver.resolve(input_fn=lambda _: "dev")

    assert len(calls) == 1


def test_unknown_dynamic_provider_is_reported():
    resolver = RuntimeValueResolver({"containers.dev.name": dynamic_prompt()}, sources={})

    with pytest.raises(ResolutionError, match="unknown dynamic options provider 'containers'"):
        resolver.resolve(input_fn=lambda _: "")


def test_prompt_formatter_styles_the_message_default_and_candidates():
    provider, _ = recording_provider((DynamicOption("dev", "running"),))
    seen: list[str] = []
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt()},
        sources={"containers": provider},
        formatter=lambda role, text: f"<{role}>{text}</>",
    )

    context = resolver.resolve(input_fn=lambda text: seen.append(text) or "")

    assert seen == [
        "  <number>1)</> <value>dev</>  <muted>running</>"
        "\n<heading>Container</> [<muted>dev</>]: "
    ]
    assert context["containers.dev.name"] == "dev"


def test_inspect_reports_the_dynamic_source():
    resolver = RuntimeValueResolver(
        {"containers.dev.name": dynamic_prompt(filter="^dev", running_only=True)}
    )

    assert resolver.inspect()["containers.dev.name"]["source"] == {
        "provider": "containers",
        "filter": "^dev",
        "running_only": True,
    }


def test_prompt_source_schema_rules():
    assert dynamic_prompt(filter="^dev").prompt.source == PromptSource(
        provider="containers", filter="^dev"
    )
    for data in (
        {
            "prompt": {
                "mode": "select",
                "message": "x",
                "options": ["a"],
                "source": {"provider": "containers"},
            }
        },
        {"prompt": {"mode": "input", "message": "x", "source": {"provider": "containers"}}},
        {"prompt": {"mode": "select", "message": "x", "source": {"provider": "containers",
                                                                 "filter": "("}}},
        {"prompt": {"mode": "select", "message": "x", "source": {"provider": "containers",
                                                                 "filtre": "^dev"}}},
        {"prompt": {"mode": "select", "message": "x", "source": {"provider": "Containers"}}},
    ):
        with pytest.raises(ValidationError):
            PromptValue.model_validate(data)


def test_target_model_performs_type_validation_after_interaction():
    template = RigyardConfig.model_validate(
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
