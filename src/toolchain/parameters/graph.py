"""Dependency graph construction and deterministic topological ordering."""

from __future__ import annotations

from collections.abc import Mapping

from ..errors import DependencyError
from .conditions import condition_dependencies
from .models import ParameterSpec


def build_dependencies(parameters: Mapping[str, ParameterSpec]) -> dict[str, set[str]]:
    dependencies: dict[str, set[str]] = {}
    known = set(parameters)
    for name, spec in parameters.items():
        refs: set[str] = set()
        if spec.enabled_if:
            refs.update(condition_dependencies(spec.enabled_if))
        if spec.required_if:
            refs.update(condition_dependencies(spec.required_if))
        unknown = refs - known
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise DependencyError(
                f"parameter {name!r} condition references unknown parameter(s): {joined}"
            )
        if name in refs:
            raise DependencyError(f"parameter {name!r} condition references itself")
        dependencies[name] = refs
    return dependencies


def topological_order(parameters: Mapping[str, ParameterSpec]) -> tuple[str, ...]:
    dependencies = build_dependencies(parameters)
    order: list[str] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> None:
        current = state.get(name, 0)
        if current == 2:
            return
        if current == 1:
            start = stack.index(name)
            cycle = stack[start:] + [name]
            raise DependencyError(f"parameter dependency cycle: {' -> '.join(cycle)}")
        state[name] = 1
        stack.append(name)
        for dependency in sorted(dependencies[name]):
            visit(dependency)
        stack.pop()
        state[name] = 2
        order.append(name)

    for parameter_name in parameters:
        visit(parameter_name)
    return tuple(order)
