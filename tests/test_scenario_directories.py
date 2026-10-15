"""Recursive source loading, source identity and interactive navigation contracts."""

from pathlib import Path

import pytest
from test_menu import TTYBuffer, write

from rigyard.application.project import ProjectContext
from rigyard.cli.menu.app import MenuApp
from rigyard.cli.menu.prompt import MenuIO
from rigyard.cli.menu.session import MenuSession
from rigyard.config.catalog import DefinitionCatalog
from rigyard.config.loader import load_config
from rigyard.config.models import ScenarioSourceNode
from rigyard.errors import ConfigIOError, SchemaValidationError

LEAF = """robot:
  instances:
    robot1:
      container: existing
      groups:
        driver: {command: [echo, ready]}
  profiles:
    development: {attach: false}
"""


def project(tmp_path):
    root = write(
        tmp_path / "rigyard.yaml",
        "version: 3\nmetadata: {name: nested}\nsources: {scenarios: [scenes/xxbot.yaml]}\n",
    )
    write(
        tmp_path / "scenes/xxbot.yaml",
        "description: XXBot\nsources: {scenarios: [nav/index.yaml, manipulation.yaml]}\n",
    )
    write(
        tmp_path / "scenes/nav/index.yaml",
        "description: Navigation\nsources: {scenarios: [simulation.yaml]}\n",
    )
    write(tmp_path / "scenes/nav/simulation.yaml", LEAF)
    write(tmp_path / "scenes/manipulation.yaml", LEAF)
    return root


def test_recursive_sources_preserve_leaf_identity_and_relative_paths(tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.chdir(tmp_path / "scenes/nav")
    config = load_config(root)
    leaves = config.source_files["scenarios"]
    assert [leaf.path for leaf in leaves] == [
        tmp_path / "scenes/nav/simulation.yaml",
        tmp_path / "scenes/manipulation.yaml",
    ]
    assert config.scenario_tree[0].children[0].children[0] is leaves[0]
    catalog = DefinitionCatalog(config, root)
    with pytest.raises(SchemaValidationError, match="ambiguous"):
        catalog.find("scenarios", "robot")
    definition = catalog.find("scenarios", "robot", Path("scenes/nav/simulation.yaml"))
    assert definition.source_path == leaves[0].path
    assert definition.value is leaves[0].definitions["robot"]


def test_reused_leaf_is_registered_once(tmp_path):
    root = project(tmp_path)
    write(tmp_path / "scenes/manipulation.yaml", "sources: {scenarios: [nav/simulation.yaml]}\n")
    config = load_config(root)
    assert len(config.source_files["scenarios"]) == 1
    assert not config.duplicate_names["scenarios"]
    assert config.scenario_tree[0].children[1].children[0] is config.source_files["scenarios"][0]


@pytest.mark.parametrize(
    "content",
    [
        "sources: {scenarios: []}\n",
        "sources: {scenarios: ['']}\n",
        "sources: {containers: other.yaml}\n",
        "sources: {scenarios: [nav/index.yaml]}\n" + LEAF,
        "description: ''\nsources: {scenarios: [nav/index.yaml]}\n",
        "sources: null\n",
    ],
)
def test_invalid_directories_fail_during_load(tmp_path, content):
    root = project(tmp_path)
    write(tmp_path / "scenes/xxbot.yaml", content)
    with pytest.raises(SchemaValidationError, match="xxbot.yaml"):
        load_config(root)


@pytest.mark.parametrize("target", ["index.yaml", "../xxbot.yaml"])
def test_cycles_report_reference_chain(tmp_path, target):
    root = project(tmp_path)
    write(tmp_path / "scenes/nav/index.yaml", f"sources: {{scenarios: [{target}]}}\n")
    with pytest.raises(SchemaValidationError, match="cyclic scenario source reference") as error:
        load_config(root)
    assert " -> " in str(error.value)
    assert "xxbot.yaml" in str(error.value)
    assert "index.yaml" in str(error.value)


def test_missing_child_fails_before_menu(tmp_path):
    root = project(tmp_path)
    (tmp_path / "scenes/nav/simulation.yaml").unlink()
    with pytest.raises(ConfigIOError, match="simulation.yaml"):
        load_config(root)


def test_existing_scene_named_sources_still_loads(tmp_path):
    root = project(tmp_path)
    write(tmp_path / "scenes/xxbot.yaml", LEAF.replace("robot:\n", "sources:\n", 1))
    assert "sources" in load_config(root).scenarios


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ("1\n1\n1\n1\n", "nav/simulation.yaml"),
        ("1\n1\n0\n2\n1\n", "manipulation.yaml"),
        ("1\n1\n1\n0\n0\n2\n1\n", "manipulation.yaml"),
        ("1\n0\n0\n", None),
    ],
)
def test_nested_menu_selection_and_back(tmp_path, answers, expected):
    root = project(tmp_path)
    session = MenuSession(ProjectContext.capture(root, config=load_config(root)))
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer(answers), output))
    result = app._select_scenario(session, "Start scene")
    if expected is None:
        assert result is None
    else:
        assert result[0].path == tmp_path / "scenes" / expected
        assert result[1:] == ("robot", "development")
    assert "Start scene / XXBot" in output.getvalue()


def test_profile_back_returns_to_scene_selection(tmp_path):
    root = project(tmp_path)
    write(tmp_path / "scenes/manipulation.yaml", LEAF + "    debug: {attach: false}\n")
    session = MenuSession(ProjectContext.capture(root, config=load_config(root)))
    app = MenuApp(MenuIO(TTYBuffer("1\n2\n1\n0\n1\n2\n"), TTYBuffer()))
    assert app._select_scenario(session, "Start scene")[2] == "debug"


def test_compose_filter_prunes_directories_without_matching_leaves(tmp_path):
    root = project(tmp_path)
    session = MenuSession(ProjectContext.capture(root, config=load_config(root)))
    assert MenuApp()._select_scenario(session, "Down scene", compose_only=True) is None
    compose = LEAF.replace("  instances:", "  compose: {file: compose.yaml}\n  instances:")
    write(
        tmp_path / "scenes/manipulation.yaml",
        compose.replace("container: existing", "service: robot"),
    )
    session = MenuSession(ProjectContext.capture(root, config=load_config(root)))
    output = TTYBuffer()
    app = MenuApp(MenuIO(TTYBuffer("1\n1\n1\n"), output))
    result = app._select_scenario(session, "Down scene", compose_only=True)
    assert result[0].path.name == "manipulation.yaml"
    assert "Navigation" not in output.getvalue()


def test_depth_limit_reports_config_error(tmp_path):
    root = project(tmp_path)
    write(tmp_path / "scenes/xxbot.yaml", "sources: {scenarios: [0.yaml]}\n")
    for index in range(65):
        write(tmp_path / f"scenes/{index}.yaml", f"sources: {{scenarios: [{index + 1}.yaml]}}\n")
    with pytest.raises(SchemaValidationError, match="nesting exceeds"):
        load_config(root)


def test_nested_cli_and_runtime_identity_survive_directory_reorganization(tmp_path):
    from rigyard.application.requests import ResolutionRequest
    from rigyard.application.scenarios import PlanScenarioUseCase
    from rigyard.cli.main import run

    root = project(tmp_path)
    source = Path("scenes/nav/simulation.yaml")
    output = TTYBuffer()
    assert (
        run(
            [
                "--config",
                str(root),
                "scene",
                "start",
                "robot",
                "development",
                "--source",
                str(source),
                "--dry-run",
                "--non-interactive",
            ],
            stdout=output,
        )
        == 0
    )
    before = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(root, source_path=source, interactive=False)
    )
    write(tmp_path / "scenes/xxbot.yaml", "sources: {scenarios: [nav/simulation.yaml]}\n")
    after = PlanScenarioUseCase().plan(
        "robot", "development", ResolutionRequest(root, source_path=source, interactive=False)
    )
    assert before.identity == after.identity
    assert before.session == after.session


@pytest.mark.parametrize("prefix_length", [62, 63])
def test_cached_subtree_obeys_depth_limit_on_every_reference(tmp_path, prefix_length):
    root = write(
        tmp_path / "rigyard.yaml",
        "version: 3\nmetadata: {name: cached-depth}\nsources: {scenarios: [shared.yaml, 0.yaml]}\n",
    )
    write(tmp_path / "shared.yaml", "sources: {scenarios: [leaf.yaml]}\n")
    write(tmp_path / "leaf.yaml", LEAF)
    for index in range(prefix_length):
        target = f"{index + 1}.yaml" if index + 1 < prefix_length else "shared.yaml"
        write(tmp_path / f"{index}.yaml", f"sources: {{scenarios: [{target}]}}\n")
    if prefix_length == 62:
        assert len(load_config(root).source_files["scenarios"]) == 1
    else:
        with pytest.raises(SchemaValidationError, match="nesting exceeds"):
            load_config(root)


@pytest.mark.parametrize("compose_only", [False, True])
def test_shared_subtree_filtering_has_bounded_work(tmp_path, monkeypatch, compose_only):
    root = write(
        tmp_path / "rigyard.yaml",
        "version: 3\nmetadata: {name: shared-filter}\nsources: {scenarios: [0.yaml]}\n",
    )
    # A small acyclic graph has exponentially many routes to its leaves.
    directory_count = 20
    for index in range(directory_count):
        write(
            tmp_path / f"{index}.yaml",
            f"sources: {{scenarios: [{index + 1}.yaml, {index + 2}.yaml]}}\n",
        )
    for index in (directory_count, directory_count + 1):
        write(tmp_path / f"{index}.yaml", LEAF if compose_only else "{}\n")
    config = load_config(root)
    session = MenuSession(ProjectContext.capture(root, config=config))
    original = ScenarioSourceNode.__getattribute__
    child_reads = 0

    def count_child_reads(self, name):
        nonlocal child_reads
        if name == "children":
            child_reads += 1
            # Check work rather than wall-clock time, and fail before a hang.
            assert child_reads <= 4 * (directory_count + 2)
        return original(self, name)

    monkeypatch.setattr(ScenarioSourceNode, "__getattribute__", count_child_reads)
    assert MenuApp()._select_scenario(session, "Select scene", compose_only=compose_only) is None
