from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rigyard.application.containers import CreateContainerUseCase
from rigyard.application.parameters import ValidateConfigUseCase
from rigyard.application.requests import ResolutionRequest
from rigyard.containers.models import ContainerSpec, ContainerTemplate
from rigyard.errors import ResolutionError
from rigyard.parameters.resolver import RuntimeValueResolver, collect_prompts, materialize_as
from rigyard.parameters.templates import (
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
        tmp_path / "rigyard.yaml",
        """version: 3
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
        tmp_path / "rigyard.yaml",
        """version: 3
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


def test_root_templates_are_explicit_immutable_and_escaped(tmp_path: Path):
    config = tmp_path / 'src' / 'robot' / '.rigyard' / 'rigyard.yaml'
    active = StringTemplateRenderer(
        TemplateContext.capture(
            {'WORKSPACE_ROOT': '/wrong'},
            config_path=config,
            workspace_root=tmp_path,
            now=NOW,
            variables={'PROJECT_ROOT': '${RIGYARD_ROOT}/..'},
        )
    )
    assert active.render('${WORKSPACE_ROOT}', 'mounts') == str(tmp_path)
    assert active.render('${PROJECT_ROOT}', 'mounts') == f'{config.parent}/..'
    assert active.render('${RIGYARD_ROOT}', 'mounts') == str(config.parent)
    assert active.render('$${PROJECT_ROOT}', 'script') == '${PROJECT_ROOT}'
    with pytest.raises(TypeError):
        active.context.roots['WORKSPACE_ROOT'] = '/wrong'
    validate_template_syntax(['${WORKSPACE_ROOT}', '${RIGYARD_ROOT}'])
    with pytest.raises(ResolutionError, match='requires a config path'):
        renderer().render('${RIGYARD_ROOT}', 'mounts')
    with pytest.raises(ResolutionError, match='invalid template'):
        StringTemplateRenderer(
            TemplateContext.capture({}, config_path=config, now=NOW)
        ).render('${PROJECT_ROOT}', 'mounts')


def test_global_variables_override_builtins_and_define_custom_names(tmp_path: Path):
    config = tmp_path / "src" / "robot" / ".rigyard" / "rigyard.yaml"
    active = StringTemplateRenderer(
        TemplateContext.capture(
            {"CONTAINER_BASE": "/runtime"},
            config_path=config,
            workspace_root=tmp_path,
            now=NOW,
            variables={
                "WORKSPACE_ROOT": "/container-workspace",
                "CONTAINER_WORKSPACE_CHILD": "${WORKSPACE_ROOT}/child",
                "PROJECT_ROOT": "${RIGYARD_ROOT}/..",
                "CONTAINER_PROJECT_ROOT": "${PROJECT_ROOT}/container",
                "CONTAINER_CACHE_ROOT": "${env:CONTAINER_BASE}/cache",
            },
        )
    )

    assert active.render("${WORKSPACE_ROOT}", "value") == "/container-workspace"
    assert active.render("${CONTAINER_WORKSPACE_CHILD}", "value") == (
        "/container-workspace/child"
    )
    assert active.render("${PROJECT_ROOT}", "value") == f"{config.parent}/.."
    assert active.render("${CONTAINER_PROJECT_ROOT}", "value") == (
        f"{config.parent}/../container"
    )
    assert active.render("${CONTAINER_CACHE_ROOT}", "value") == "/runtime/cache"


def test_container_plan_uses_manifest_global_variables(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: variables}
variables:
  WORKSPACE_ROOT: /container-workspace
  CONTAINER_PROJECT_ROOT: /container-workspace/project
sources: {containers: containers.yaml}
""",
    )
    write(
        tmp_path / "containers.yaml",
        """development:
  image: ubuntu
  mounts: ["${WORKSPACE_ROOT}:/host-workspace"]
  environment:
    PROJECT_ROOT: "${CONTAINER_PROJECT_ROOT}"
""",
    )

    plan = CreateContainerUseCase(backend=None).plan(
        "development", ResolutionRequest(config, interactive=False), environment={}, now=NOW
    )

    assert {(mount.source, mount.target) for mount in plan.mounts} == {
        ("/container-workspace", "/host-workspace")
    }
    assert dict(plan.environment)["PROJECT_ROOT"] == "/container-workspace/project"


def test_validate_accepts_references_to_previous_user_variables(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: variables}
variables:
  CONTAINER_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: ${CONTAINER_ROOT}/project
sources: {containers: containers.yaml}
""",
    )
    write(tmp_path / "containers.yaml", "development: {image: ubuntu}\n")

    ValidateConfigUseCase().execute(config)

    active = StringTemplateRenderer(
        TemplateContext.capture(
            {},
            config_path=config,
            now=NOW,
            variables={
                "CONTAINER_ROOT": "/workspace",
                "CONTAINER_PROJECT_ROOT": "${CONTAINER_ROOT}/project",
            },
        )
    )
    assert active.render("${CONTAINER_PROJECT_ROOT}", "value") == "/workspace/project"


def test_validate_rejects_forward_global_variable_references(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: variables}
variables:
  CONTAINER_PROJECT_ROOT: ${CONTAINER_ROOT}/project
  CONTAINER_ROOT: /workspace
sources: {containers: containers.yaml}
""",
    )
    write(tmp_path / "containers.yaml", "development: {image: ubuntu}\n")

    with pytest.raises(ResolutionError, match="variables.CONTAINER_PROJECT_ROOT"):
        ValidateConfigUseCase().execute(config)


def test_validate_accepts_custom_global_variables_in_source_templates(tmp_path: Path):
    config = write(
        tmp_path / "rigyard.yaml",
        """version: 3
metadata: {name: variables}
variables: {CONTAINER_WORKSPACE_ROOT: /workspace}
sources: {containers: containers.yaml}
""",
    )
    write(
        tmp_path / "containers.yaml",
        """development:
  image: ubuntu
  workdir: ${CONTAINER_WORKSPACE_ROOT}
""",
    )

    ValidateConfigUseCase().execute(config)


@pytest.mark.parametrize('initialized', [False, True])
def test_container_roots_follow_workspace_binding(tmp_path: Path, monkeypatch, initialized):
    from rigyard.workspace import initialize_workspace, resolve_config_path

    config_dir = tmp_path / 'src' / 'robot' / '.rigyard'
    config = write(
        config_dir / 'rigyard.yaml',
        'version: 3\nmetadata: {name: roots}\n'
        'variables: {PROJECT_ROOT: "${RIGYARD_ROOT}/.."}\n'
        'sources: {containers: containers.yaml}\n',
    )
    write(
        config_dir / 'containers.yaml',
        '''development:
  image: ubuntu
  mounts:
    - "${WORKSPACE_ROOT}:/workspace"
    - "${PROJECT_ROOT}:/project"
  environment:
    CONFIG_ROOT: "${RIGYARD_ROOT}"
''',
    )
    monkeypatch.chdir(tmp_path)
    if initialized:
        initialize_workspace(config)
    selected = resolve_config_path(None if initialized else config)
    plan = CreateContainerUseCase(backend=None).plan(
        'development', ResolutionRequest(selected, interactive=False), environment={}, now=NOW,
    )
    mounts = {(mount.source, mount.target) for mount in plan.mounts}
    assert (str(tmp_path), '/workspace') in mounts
    assert (str(config_dir.parent), '/project') in mounts
    assert dict(plan.environment)['CONFIG_ROOT'] == str(config_dir)


def test_project_root_can_be_defined_explicitly_for_flat_config_layout(tmp_path: Path):
    active = StringTemplateRenderer(
        TemplateContext.capture(
            {},
            config_path=tmp_path / 'rigyard.yaml',
            now=NOW,
            variables={'PROJECT_ROOT': '${RIGYARD_ROOT}'},
        )
    )
    assert active.render('${PROJECT_ROOT}', 'value') == str(tmp_path)
    assert active.render('${RIGYARD_ROOT}', 'value') == str(tmp_path)


def test_image_alias_supports_templates_and_prompt_defaults(tmp_path):
    from rigyard.application.images import BuildImageUseCase
    from rigyard.application.requests import BuildImageRequest

    config = write(tmp_path / 'rigyard.yaml',
                   'version: 3\nmetadata: {name: alias}\nsources: {images: images.yaml}\n')
    write(tmp_path / 'layer.Dockerfile', 'RUN true\n')
    write(tmp_path / 'images.yaml', '''development:
  base: ubuntu
  tag: "example:dev_${date:%Y%m%d}"
  tag_alias:
    default: "example:dev_${env:ARCH}"
    prompt: {mode: input, message: Alias}
  layers:
    - {name: system, dockerfile: layer.Dockerfile}
''')
    plan = BuildImageUseCase(None).plan(
        BuildImageRequest(config, 'development', interactive=False),
        environment={'ARCH': 'x86_64'}, now=NOW,
    )
    assert plan.final_tag == 'example:dev_20260916'
    assert plan.tag_alias == 'example:dev_x86_64'
