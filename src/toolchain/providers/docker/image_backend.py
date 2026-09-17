"""Image build backend implemented with the locally configured Docker CLI."""

from __future__ import annotations

from ...errors import BackendUnavailableError, ImageBuildError
from ...images.models import BuildStepResult, ImageBuildStep
from .dockerfile import compose_dockerfile
from .runner import CommandRunner, SubprocessRunner


class DockerImageBackend:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def check_available(self) -> None:
        command = ("docker", "version", "--format", "{{.Server.Version}}")
        try:
            result = self.runner.run(command, capture=True)
        except FileNotFoundError as exc:
            raise BackendUnavailableError("Docker CLI executable was not found") from exc
        if result.returncode != 0:
            detail = _detail(result.stderr, result.stdout)
            raise BackendUnavailableError(
                f"Docker daemon is unavailable (exit {result.returncode}){detail}"
            )

    def tag_image(self, source: str, alias: str) -> None:
        try:
            result = self.runner.run(("docker", "tag", source, alias), capture=True)
        except OSError as exc:
            raise BackendUnavailableError(f"cannot execute Docker tag: {exc}") from exc
        if result.returncode:
            raise ImageBuildError(
                f"image {source!r} was built but tagging alias {alias!r} failed "
                f"(exit {result.returncode}){_detail(result.stderr, result.stdout)}"
            )

    def build_step(self, step: ImageBuildStep) -> BuildStepResult:
        command: list[str] = ["docker", "build", "--file", "-", "--tag", step.output_tag]
        for name, value in step.build_args.items():
            command.extend(("--build-arg", f"{name}={value}"))
        command.append(str(step.context))
        argv = tuple(command)
        try:
            result = self.runner.run(
                argv,
                stdin=compose_dockerfile(step.base_image, step.dockerfile_fragment),
            )
        except FileNotFoundError as exc:
            raise BackendUnavailableError("Docker CLI executable was not found") from exc
        if result.returncode != 0:
            detail = _detail(result.stderr, result.stdout)
            raise ImageBuildError(
                f"image layer {step.index} ({step.layer_name!r}) failed while building "
                f"{step.output_tag!r} from {step.base_image!r} "
                f"(exit {result.returncode}){detail}"
            )
        return BuildStepResult(
            index=step.index,
            layer_name=step.layer_name,
            output_tag=step.output_tag,
            command=argv,
        )


def _detail(stderr: str, stdout: str) -> str:
    message = stderr.strip() or stdout.strip()
    return f": {message}" if message else ""
