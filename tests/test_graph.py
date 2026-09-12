import pytest

from toolchain.errors import DependencyError
from toolchain.graph import topological_order
from toolchain.models import ParameterSchema


def schema(parameters):
    return ParameterSchema.model_validate({"version": 1, "parameters": parameters})


def test_dependency_order_is_stable() -> None:
    model = schema(
        {
            "device": {"enabled_if": {"mode": "hardware"}},
            "mode": {"type": "choice", "options": ["simulation", "hardware"]},
            "debug": {"type": "bool"},
        }
    )
    assert topological_order(model.parameters) == ("mode", "device", "debug")


def test_unknown_dependency_is_rejected() -> None:
    model = schema({"device": {"enabled_if": {"missing": True}}})
    with pytest.raises(DependencyError, match="unknown parameter"):
        topological_order(model.parameters)


def test_cycle_is_rejected() -> None:
    model = schema(
        {
            "a": {"enabled_if": {"b": True}},
            "b": {"enabled_if": {"a": True}},
        }
    )
    with pytest.raises(DependencyError, match="a -> b -> a"):
        topological_order(model.parameters)

