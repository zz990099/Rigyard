"""Structured, non-executable condition grammar."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import RootModel

ConditionData = dict[str, Any]


class Condition(RootModel[ConditionData]):
    """A condition represented by equality mappings or all/any/not operators."""

    def dependencies(self) -> set[str]:
        return condition_dependencies(self.root)

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return evaluate_condition(self.root, values)


def validate_condition(data: Any, path: str = "condition") -> ConditionData:
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path} must be a non-empty mapping")

    operators = {"all", "any", "not"}.intersection(data)
    if operators:
        if len(data) != 1:
            raise ValueError(f"{path} operator form must contain exactly one key")
        operator = next(iter(operators))
        operand = data[operator]
        if operator in {"all", "any"}:
            if not isinstance(operand, list) or not operand:
                raise ValueError(f"{path}.{operator} must be a non-empty list")
            for index, child in enumerate(operand):
                validate_condition(child, f"{path}.{operator}[{index}]")
        else:
            validate_condition(operand, f"{path}.not")
        return data

    for key in data:
        if not isinstance(key, str) or not key:
            raise ValueError(f"{path} parameter names must be non-empty strings")
    return data


def condition_dependencies(data: ConditionData) -> set[str]:
    if "all" in data:
        return set().union(*(condition_dependencies(item) for item in data["all"]))
    if "any" in data:
        return set().union(*(condition_dependencies(item) for item in data["any"]))
    if "not" in data:
        return condition_dependencies(data["not"])
    return set(data)


def evaluate_condition(data: ConditionData, values: Mapping[str, Any]) -> bool:
    if "all" in data:
        return all(evaluate_condition(item, values) for item in data["all"])
    if "any" in data:
        return any(evaluate_condition(item, values) for item in data["any"])
    if "not" in data:
        return not evaluate_condition(data["not"], values)
    return all(values.get(name) == expected for name, expected in data.items())

