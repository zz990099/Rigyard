from types import MappingProxyType

import pytest

from toolchain.context import ValueSource
from toolchain.engine import ParameterEngine
from toolchain.errors import DependencyError, MissingValueError, ResolutionError
from toolchain.models import ParameterSchema


def engine(parameters) -> ParameterEngine:
    model = ParameterSchema.model_validate({"version": 1, "parameters": parameters})
    return ParameterEngine(model)


def test_precedence_and_source_metadata() -> None:
    resolver = engine({"count": {"type": "int", "default": 1}})
    context = resolver.resolve(
        values={"count": 2},
        environ={"TOOL_PARAM_COUNT": "3"},
        overrides={"count": "4"},
        interactive=False,
    )
    assert context["count"] == 4
    assert context.resolved("count").source == ValueSource.CLI


def test_each_precedence_layer() -> None:
    resolver = engine({"count": {"type": "int", "default": 1}})
    assert resolver.resolve(environ={}, interactive=False)["count"] == 1
    assert resolver.resolve(values={"count": 2}, environ={}, interactive=False)["count"] == 2
    assert (
        resolver.resolve(
            values={"count": 2}, environ={"TOOL_PARAM_COUNT": "3"}, interactive=False
        )["count"]
        == 3
    )


def test_conditions_disable_and_require_parameters() -> None:
    resolver = engine(
        {
            "mode": {
                "type": "choice",
                "options": ["simulation", "hardware"],
                "default": "simulation",
            },
            "device": {"enabled_if": {"mode": "hardware"}, "required": True},
            "name": {"required_if": {"mode": "simulation"}},
        }
    )
    with pytest.raises(MissingValueError) as caught:
        resolver.resolve(environ={}, interactive=False)
    assert caught.value.names == ("name",)

    context = resolver.resolve(
        values={"name": "sim"}, environ={}, interactive=False
    )
    assert "device" not in context
    assert context.disabled == frozenset({"device"})


def test_interactive_prompt_fills_required_value() -> None:
    resolver = engine({"count": {"type": "int", "required": True}})
    responses = iter(["5"])
    context = resolver.resolve(environ={}, input_fn=lambda _: next(responses))
    assert context["count"] == 5
    assert context.resolved("count").source == ValueSource.INTERACTIVE


def test_noninteractive_reports_all_missing_values() -> None:
    resolver = engine(
        {
            "first": {"required": True},
            "second": {"required": True},
        }
    )
    with pytest.raises(MissingValueError) as caught:
        resolver.resolve(environ={}, interactive=False)
    assert caught.value.names == ("first", "second")


def test_unknown_values_are_rejected() -> None:
    resolver = engine({"known": {}})
    with pytest.raises(ResolutionError, match="unknown parameter"):
        resolver.resolve(values={"unknown": 1}, environ={}, interactive=False)


def test_context_is_immutable() -> None:
    resolver = engine({"name": {"default": "robot"}})
    context = resolver.resolve(environ={}, interactive=False)
    assert context["name"] == "robot"
    assert isinstance(context._resolved, MappingProxyType)
    with pytest.raises(TypeError):
        context._resolved["name"] = "changed"


def test_environment_name_collision_is_rejected() -> None:
    with pytest.raises(ResolutionError, match="same environment variable"):
        engine({"build.type": {}, "build-type": {}})


def test_self_dependency_is_rejected() -> None:
    with pytest.raises(DependencyError, match="references itself"):
        engine({"mode": {"enabled_if": {"mode": True}}})

