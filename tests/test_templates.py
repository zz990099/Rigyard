from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from toolchain.application.containers import CreateContainerUseCase
from toolchain.application.parameters import ValidateConfigUseCase
from toolchain.application.requests import ResolutionRequest
from toolchain.containers.models import ContainerSpec, ContainerTemplate
from toolchain.errors import ResolutionError
from toolchain.parameters.resolver import RuntimeValueResolver, collect_prompts, materialize_as
from toolchain.parameters.templates import (
    StringTemplateRenderer,
    TemplateContext,
    validate_template_syntax,
)

NOW = datetime(2026, 9, 16, 10, 30, 45, tzinfo=timezone(timedelta(hours=8)))


def renderer(environment=None) -> StringTemplateRenderer:
    return StringTemplateRenderer(TemplateContext.capture(environment or {}, now=NOW))


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_environment_local_date_and_utcdate_render_together():
    value = "dev_${env:USER}_${date:%Y%m%d%H%M}_${utcdate:%Y%m%d%H%M}"

    assert renderer({"USER": "alice"}).render(value, "containers.dev.name") == (
        "dev_alice_202609161030_202609160230"
    )


def test_escape_and_environment_replacements_are_not_evaluated_recursively():
    active = renderer({"USER": "${date:%Y}"})

    assert active.render("$${env:USER}-${env:USER}", "value") == ("${env:USER}-${date:%Y}")


@pytest.mark.parametrize(
    "value,message",
    [
        ("${env:MISSING}", "missing environment variable"),
        ("${unknown:value}", "unsupported template kind"),
        ("${env:bad-name}", "invalid environment variable name"),
        ("${date:%Q}", "unsupported date directive"),
        ("${date:%}", "incomplete '%' directive"),
        ("${env:USER", "unterminated template"),
        ("${env}", "expected KIND:ARGUMENT"),
        ("${date:%Y${env:USER}}", "nested templates are not supported"),
        ("${env:NUL}", "NUL bytes are not allowed"),
    ],
)
def test_template_errors_include_configuration_path(value, message):
    environment = {"NUL": "bad\x00value"} if "NUL" in value else None
    with pytest.raises(ResolutionError, match=message) as error:
        renderer(environment).render(value, "containers.dev.name")

    assert "containers.dev.name" in str(error.value)


def test_materialization_renders_prompt_results_lists_and_paths():
    template = ContainerTemplate.model_validate(
        {
            "image": "registry/${env:USER}:latest",
            "name": {
                "default": "dev_${env:USER}_${date:%Y%m%d%H%M}",
                "prompt": {"mode": "input", "message": "Name"},
            },
            "mounts": ["/home/${env:USER}:/workspace"],
            "workdir": "/workspace/${env:USER}",
        }
    )
    prefix = "containers.dev"
    context = RuntimeValueResolver(collect_prompts(template, prefix)).resolve(interactive=False)

    spec = materialize_as(
        template,
        prefix,
        context,
        ContainerSpec,
        renderer({"USER": "alice"}),
    )

    assert spec.image == "registry/alice:latest"
    assert spec.name == "dev_alice_202609161030"
    assert spec.mounts == ("/home/alice:/workspace",)
    assert spec.workdir == "/workspace/alice"


def test_validate_checks_syntax_without_requiring_environment(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 2
metadata: {name: templates}
sources: {containers: containers.yaml}
""",
    )
    source = write(
        tmp_path / "containers.yaml",
        """good: {image: ubuntu, name: "dev_${env:MISSING}"}
bad: {image: ubuntu, name: "${unknown:value}"}
""",
    )

    with pytest.raises(ResolutionError, match="containers.bad.name"):
        ValidateConfigUseCase().execute(config)

    source.write_text('good: {image: ubuntu, name: "dev_${env:MISSING}"}\n')
    ValidateConfigUseCase().execute(config)


def test_selected_operation_does_not_expand_other_templates(tmp_path: Path):
    config = write(
        tmp_path / "toolchain.yaml",
        """version: 2
metadata: {name: templates}
sources: {containers: containers.yaml}
""",
    )
    write(
        tmp_path / "containers.yaml",
        """selected:
  image: ubuntu
  name: "dev_${env:USER}_${date:%Y%m%d%H%M}"
  environment:
    RUN_ID: "${utcdate:%Y%m%d%H%M}"
unselected:
  image: ubuntu
  name: "${env:MISSING}"
""",
    )

    plan = CreateContainerUseCase(backend=None).plan(
        "selected",
        ResolutionRequest(config, interactive=False),
        environment={"USER": "alice"},
        now=NOW,
    )

    assert plan.container_name == "dev_alice_202609161030"
    assert dict(plan.environment) == {"RUN_ID": "202609160230"}


def test_syntax_validation_handles_nested_values_and_escaped_literals():
    validate_template_syntax(
        {"items": ["${env:MISSING}", Path("${date:%Y%m%d}"), "$${unknown:value}"]}
    )
