"""Composition root for Docker, Compose, and tmux scenario adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..execution import CommandRunner
from .lifecycle import ComposeLifecycleBackend, ContainerLifecycleBackend
from .ports import ComposeRuntime, ContainerRuntime, SessionRuntime
from .runtime import ScenarioCommandGateway
from .tmux import TmuxSessionBackend


def runtime_backends(
    runner: CommandRunner,
    environment: Mapping[str, str],
    sleep: Callable[[float], None],
) -> tuple[ContainerRuntime, ComposeRuntime, SessionRuntime]:
    commands = ScenarioCommandGateway(runner)
    return (
        ContainerLifecycleBackend(commands, sleep),
        ComposeLifecycleBackend(commands, environment),
        TmuxSessionBackend(commands, runner, environment),
    )
