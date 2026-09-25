"""Dynamic image candidates backed by the Docker CLI."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ...execution import CommandRunner, SubprocessRunner
from ...parameters.sources import DynamicOption, DynamicOptionsProvider, PromptSource

PROVIDER_NAME = "docker-images"
IMAGE_FORMAT = "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}"


def _short_image_id(image_id: str) -> str:
    digest = image_id.removeprefix("sha256:")
    return digest[:12]


def docker_images_source(runner: CommandRunner | None = None) -> DynamicOptionsProvider:
    """List locally tagged images for a select prompt.

    A missing daemon, a failing command or a missing executable yields no candidates
    so the prompt falls back to free-form input instead of blocking the command.
    Dangling images are omitted because they have no stable repository/tag reference.
    """

    command_runner = runner or SubprocessRunner()

    def provide(source: PromptSource) -> Sequence[DynamicOption]:
        command = (
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--format",
            IMAGE_FORMAT,
        )
        try:
            result = command_runner.run(command, capture=True)
        except OSError:
            return ()
        if result.returncode:
            return ()
        pattern = re.compile(source.filter) if source.filter else None
        options = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            repository, tag = (field.strip() for field in fields[:2])
            if not repository or not tag or "<none>" in (repository, tag):
                continue
            reference = f"{repository}:{tag}"
            if pattern is not None and not pattern.search(reference):
                continue
            image_id = fields[2].strip() if len(fields) > 2 else ""
            details = [_short_image_id(image_id)] if image_id else []
            details.extend(field.strip() for field in fields[3:] if field.strip())
            options.append(DynamicOption(reference, ", ".join(details) or None))
        return tuple(sorted(options, key=lambda option: option.value))

    return provide


def docker_image_sources(
    runner: CommandRunner | None = None,
) -> dict[str, DynamicOptionsProvider]:
    """Provider registry for prompts that select a local Docker image."""

    return {PROVIDER_NAME: docker_images_source(runner)}
