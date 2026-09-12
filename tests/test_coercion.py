from pathlib import Path

import pytest

from toolchain.coercion import coerce_value
from toolchain.errors import ResolutionError
from toolchain.models import ParameterSpec


@pytest.mark.parametrize(
    ("definition", "raw", "expected"),
    [
        ({"type": "string"}, 42, "42"),
        ({"type": "int", "min": 1}, "3", 3),
        ({"type": "float", "max": 2.5}, "2.25", 2.25),
        ({"type": "bool"}, "yes", True),
        ({"type": "choice", "options": ["a", "b"]}, "b", "b"),
        ({"type": "path"}, "~/work", Path("~/work").expanduser()),
        ({"type": "list", "item_type": "int"}, "1,2,3", [1, 2, 3]),
    ],
)
def test_supported_types(definition, raw, expected) -> None:
    assert coerce_value("value", raw, ParameterSpec.model_validate(definition)) == expected


@pytest.mark.parametrize(
    ("definition", "raw"),
    [
        ({"type": "int", "min": 2}, "1"),
        ({"type": "string", "pattern": "[a-z]+"}, "ABC"),
        ({"type": "choice", "options": ["a"]}, "b"),
        ({"type": "bool"}, "perhaps"),
    ],
)
def test_constraints_are_enforced(definition, raw) -> None:
    with pytest.raises(ResolutionError, match="invalid value"):
        coerce_value("value", raw, ParameterSpec.model_validate(definition))

