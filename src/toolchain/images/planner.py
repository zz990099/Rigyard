"""Turn an image definition and parameter context into deterministic build steps."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..errors import ImageConfigError, ImagePlanError, SourceLocation
from .models import ImageBuildPlan, ImageBuildStep, ImageSpec

FROM_INSTRUCTION = re.compile(r"^\s*FROM(?:\s|$)", re.IGNORECASE | re.MULTILINE)
PARSER_DIRECTIVE = re.compile(r"^\s*#\s*(?:syntax|escape)\s*=", re.IGNORECASE | re.MULTILINE)
UNSAFE_REFERENCE = re.compile(r"[\s\x00-\x1f]")


class ImageBuildPlanner:
    def create_plan(
        self,
        image_name: str,
        spec: ImageSpec,
        config_path: str | Path,
    ) -> ImageBuildPlan:
        config_file = Path(config_path).resolve()
        project_dir = config_file.parent
        build_context = _resolve_path(project_dir, spec.context)
        if not build_context.is_dir():
            raise ImageConfigError(
                f"image {image_name!r} context is not a directory: {build_context}",
                SourceLocation(config_file),
            )

        base = spec.base
        final_tag = spec.tag
        _validate_reference(base, f"images.{image_name}.base")
        _validate_reference(final_tag, f"images.{image_name}.tag", output=True)

        if spec.tag_alias is not None:
            _validate_reference(spec.tag_alias, f"images.{image_name}.tag_alias", output=True)
            if not spec.tag_alias or spec.tag_alias.startswith("-"):
                raise ImagePlanError(f"images.{image_name}.tag_alias must be a non-empty image tag")

        steps: list[ImageBuildStep] = []
        previous = base
        for index, layer in enumerate(spec.layers, start=1):
            layer_path = _resolve_path(project_dir, layer.dockerfile)
            fragment = _read_fragment(layer_path, image_name, layer.name)
            sources = {**spec.build_args, **layer.build_args}
            build_args = {
                name: str(value).lower() if isinstance(value, bool) else str(value)
                for name, value in sorted(sources.items())
            }
            output_tag = (
                final_tag
                if index == len(spec.layers)
                else _intermediate_tag(config_file, image_name, index, layer.name)
            )
            steps.append(
                ImageBuildStep(
                    index=index,
                    layer_name=layer.name,
                    base_image=previous,
                    output_tag=output_tag,
                    context=build_context,
                    dockerfile_fragment=fragment,
                    build_args=build_args,
                )
            )
            previous = output_tag

        return ImageBuildPlan(
            image_name=image_name, final_tag=final_tag, steps=tuple(steps), tag_alias=spec.tag_alias
        )


def _resolve_path(project_dir: Path, configured: Path) -> Path:
    path = configured.expanduser()
    return (project_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _read_fragment(path: Path, image_name: str, layer_name: str) -> str:
    field = f"images.{image_name}.layers.{layer_name}.dockerfile"
    try:
        fragment = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImageConfigError(f"cannot read {field}: {exc}", SourceLocation(path)) from exc
    if FROM_INSTRUCTION.search(fragment):
        raise ImageConfigError(
            f"{field} must be a Dockerfile fragment and cannot contain FROM",
            SourceLocation(path),
        )
    if PARSER_DIRECTIVE.search(fragment):
        raise ImageConfigError(
            f"{field} cannot contain Docker parser directives in schema v2",
            SourceLocation(path),
        )
    if not fragment.strip():
        raise ImageConfigError(f"{field} must not be empty", SourceLocation(path))
    return fragment.rstrip() + "\n"


def _validate_reference(value: str, field: str, *, output: bool = False) -> None:
    if UNSAFE_REFERENCE.search(value):
        raise ImagePlanError(f"{field} contains whitespace or control characters")
    if output and "@" in value:
        raise ImagePlanError(f"{field} must be a tag, not an immutable digest")


def _intermediate_tag(config_file: Path, image_name: str, index: int, layer_name: str) -> str:
    project_id = hashlib.sha256(str(config_file).encode()).hexdigest()[:12]
    image_slug = re.sub(r"[^a-z0-9_.-]", "-", image_name.lower())
    layer_slug = re.sub(r"[^a-z0-9_.-]", "-", layer_name.lower())
    return f"toolchain.local/{project_id}/{image_slug}:{index:02d}-{layer_slug}"
