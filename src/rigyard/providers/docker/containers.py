"""Dynamic select candidates backed by the Docker CLI."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ...execution import CommandRunner, SubprocessRunner
from ...parameters.sources import DynamicOption, DynamicOptionsProvider, PromptSource

PROVIDER_NAME = "docker-containers"
CONTAINER_FORMAT = "{{.Names}}\t{{.State}}\t{{.Image}}"


def docker_containers_source(runner: CommandRunner | None = None) -> DynamicOptionsProvider:
    """List containers for a select prompt.

    A missing daemon, a failing command or a missing executable yields no candidates
    so the prompt falls back to free-form input instead of blocking the command.
    """

    command_runner = runner or SubprocessRunner()

    def provide(source: PromptSource) -> Sequence[DynamicOption]:
        command = ["docker", "ps"]
        if not source.running_only:
            command.append("-a")
        command += ["--format", CONTAINER_FORMAT]
        try:
            result = command_runner.run(tuple(command), capture=True)
        except OSError:
            return ()
        if result.returncode:
            return ()
        pattern = re.compile(source.filter) if source.filter else None
        options = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            name = fields[0].strip()
            if not name or (pattern is not None and not pattern.search(name)):
                continue
            label = ", ".join(field.strip() for field in fields[1:] if field.strip())
            options.append(DynamicOption(name, label or None))
        return tuple(sorted(options, key=lambda option: option.value))

    return provide


def docker_container_sources(
    runner: CommandRunner | None = None,
) -> dict[str, DynamicOptionsProvider]:
    """Provider registry for prompts that select an existing container."""

    return {PROVIDER_NAME: docker_containers_source(runner)}
