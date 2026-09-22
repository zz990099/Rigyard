"""One-shot interactive frontend for primary rigyard operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...application.builds import BuildProjectUseCase
from ...application.containers import CreateContainerUseCase
from ...application.images import BuildImageUseCase
from ...application.parameters import ValidateConfigUseCase
from ...application.project import ProjectContext
from ...application.requests import BuildImageRequest, ResolutionRequest
from ...application.scenarios import PlanScenarioUseCase
from ...application.tasks import ExecuteTaskUseCase
from ...application.tests import ExecuteTestUseCase
from ...config.models import SourceFileInfo
from ...parameters.sources import DynamicSources
from ...providers.docker import (
    DockerExecBuildBackend,
    DockerExecTaskBackend,
    DockerExecTestBackend,
    DockerImageBackend,
    docker_sources,
)
from ...providers.docker.container_backend import DockerContainerBackend
from ...scenarios.executor import ScenarioExecutor
from ...scenarios.service import ScenarioService
from ...tests.models import TestAction
from ..branding import DEFAULT_LOGO
from ..build_output import describe_build
from ..container_output import describe_container
from ..scenario_output import describe_scenario, describe_scenario_target
from ..task_output import describe_task
from ..test_output import describe_test
from .catalog import build_default_registry
from .model import MenuAction
from .prompt import MenuIO
from .session import MenuSession

BackendFactory = Callable[[], Any]
ScenarioExecutorFactory = Callable[[], ScenarioExecutor]


class MenuApp:
    def __init__(
        self,
        io: MenuIO | None = None,
        backend_factory: BackendFactory | None = None,
        container_backend_factory: BackendFactory | None = None,
        build_backend_factory: BackendFactory | None = None,
        test_backend_factory: BackendFactory | None = None,
        task_backend_factory: BackendFactory | None = None,
        scenario_executor_factory: ScenarioExecutorFactory | None = None,
        sources: DynamicSources | None = None,
    ) -> None:
        self.io = io or MenuIO()
        self.sources = dict(docker_sources() if sources is None else sources)
        self.backend_factory = backend_factory or DockerImageBackend
        self.container_backend_factory = container_backend_factory or (
            # Replacing an existing container stays an explicit "no" by default.
            lambda: DockerContainerBackend(
                confirm_replace=lambda message: self.io.confirm(message, default=False)
            )
        )
        self.build_backend_factory = build_backend_factory or DockerExecBuildBackend
        self.test_backend_factory = test_backend_factory or DockerExecTestBackend
        self.task_backend_factory = task_backend_factory or DockerExecTaskBackend
        self.scenario_executor_factory = scenario_executor_factory or ScenarioExecutor
        self.registry = build_default_registry(
            build_image=self._build_image,
            create_container=self._create_container,
            build_project=self._build_project,
            scene_menu=self._scene_menu,
            test_menu=self._test_menu,
            task_menu=self._task_menu,
            has_menu_tasks=self._has_menu_tasks,
        )

    def run(
        self,
        config_path: str | Path = Path("rigyard.yaml"),
        values_path: str | Path | None = None,
    ) -> int:
        config_file = Path(config_path)
        values_file = Path(values_path) if values_path is not None else None
        config = ValidateConfigUseCase().execute(config_file)
        session = MenuSession(
            ProjectContext.capture(config_file, config=config),
            values_file,
        )

        try:
            logo = session.config.branding.logo or DEFAULT_LOGO
            self.io.write(self.io.style.render("title", logo))
            self.io.write()
            self.io.write_field(f"Project: {session.config.metadata.name}")
            self.io.write_field(f"Configuration: {session.config_path}")
            labels = [self._action_label(action, session) for action in self.registry.actions]
            selected = self.io.select(
                None,
                labels,
                back_label="Exit",
            )
            if selected is None:
                return 0
            action = self.registry.actions[selected]
            if not action.enabled(session):
                self.io.write_note(f"Unavailable: {action.disabled_reason}", "warning")
                return 2
            result = action.handler(session)
            return 0 if result is None else result
        except EOFError:
            self.io.write()
            return 0
        except KeyboardInterrupt:
            self.io.write("\nInterrupted")
            return 130

    def _action_label(self, action: MenuAction, session: MenuSession) -> str:
        if action.enabled(session):
            return action.label
        return f"{action.label} [{action.disabled_reason}]"

    def _source_groups(
        self,
        session: MenuSession,
        kind: str,
        *,
        requirement: Callable[[SourceFileInfo, str], bool] | None = None,
    ) -> tuple[SourceFileInfo, ...]:
        return tuple(
            group
            for group in session.config.source_files.get(kind, ())
            if group.names
            and (requirement is None or any(requirement(group, name) for name in group.names))
        )

    def _source_relative_path(self, session: MenuSession, path: Path) -> Path:
        try:
            return path.relative_to(session.config_path.resolve().parent)
        except ValueError:
            return path

    def _source_labels(self, session: MenuSession, groups: tuple[SourceFileInfo, ...]) -> list[str]:
        labels = []
        for group in groups:
            path = str(self._source_relative_path(session, group.path))
            label = f"{group.description} ({path})" if group.description else path
            labels.append(label)
        return labels

    def _select_source_group(
        self,
        session: MenuSession,
        kind: str,
        title: str,
        *,
        requirement: Callable[[SourceFileInfo, str], bool] | None = None,
    ) -> SourceFileInfo | None:
        groups = self._source_groups(session, kind, requirement=requirement)
        if not groups:
            return None
        if len(groups) == 1:
            return groups[0]
        selected = self.io.select(
            title,
            self._source_labels(session, groups),
            back_label="Back",
        )
        if selected is None:
            return None
        return groups[selected]

    def _definition_label(self, group: SourceFileInfo, name: str) -> str:
        description = getattr(group.definitions[name], "description", None)
        return f"{name} — {description}" if description else name

    def _request(
        self,
        session: MenuSession,
        source_path: Path | None = None,
        *,
        interactive: bool = True,
    ) -> ResolutionRequest:
        return ResolutionRequest(
            config_path=session.config_path,
            values_path=session.values_path,
            interactive=interactive,
            input_fn=self.io.ask,
            source_path=source_path,
            project=session.project,
        )

    def _create_container(self, session: MenuSession) -> None:
        group = self._select_source_group(session, "containers", "Create container")
        if group is None:
            return
        names = list(group.names)
        labels = [self._definition_label(group, name) for name in names]
        selected = self.io.select("Create container", labels, back_label="Back")
        if selected is None:
            return
        use_case = CreateContainerUseCase(
            self.container_backend_factory(),
            sources=self.sources,
            formatter=self.io.style.render,
        )
        plan = use_case.plan(names[selected], self._request(session, group.path))
        for line in describe_container(plan):
            self.io.write_field(line)
        if not self.io.confirm("Create and start this container now?", default=True):
            self.io.write_note("Container creation cancelled.", "muted")
            return
        result = use_case.execute(plan)
        self.io.write_note(
            f"Created and started {result.container_name} ({result.container_id}); "
            f"completed {len(result.hooks)} lifecycle hook(s)",
            "success",
        )

    def _build_image(self, session: MenuSession) -> None:
        group = self._select_source_group(session, "images", "Build image")
        if group is None:
            return
        image_names = list(group.names)
        labels = [self._definition_label(group, name) for name in image_names]
        selected = self.io.select("Build image", labels, back_label="Back")
        if selected is None:
            return
        image_name = image_names[selected]
        use_case = BuildImageUseCase(
            self.backend_factory(),
            sources=self.sources,
            formatter=self.io.style.render,
        )
        plan = use_case.plan(
            BuildImageRequest(
                config_path=session.config_path,
                image_name=image_name,
                values_path=session.values_path,
                interactive=True,
                input_fn=self.io.ask,
                source_path=group.path,
                project=session.project,
            )
        )
        self.io.write_field(f"Image: {plan.final_tag}; layers: {len(plan.steps)}")
        if plan.tag_alias is not None:
            self.io.write_field(f"Alias: {plan.tag_alias}")
        if not self.io.confirm(f"Build {image_name} now?", default=True):
            self.io.write_note("Build cancelled.", "muted")
            return
        result = use_case.execute(plan)
        self.io.write_note(f"Built {result.final_tag} ({len(result.steps)} layer(s))", "success")

    def _build_project(self, session: MenuSession) -> None:
        group = self._select_source_group(session, "builds", "Build project")
        if group is None:
            return
        names = list(group.names)
        labels = [self._definition_label(group, name) for name in names]
        selected = self.io.select("Build project", labels, back_label="Back")
        if selected is None:
            return
        use_case = BuildProjectUseCase(
            self.build_backend_factory(),
            sources=self.sources,
            formatter=self.io.style.render,
        )
        plan = use_case.plan(names[selected], self._request(session, group.path))
        for line in describe_build(plan):
            self.io.write_field(line)
        if not self.io.confirm("Run this build now?", default=True):
            self.io.write_note("Build cancelled.", "muted")
            return
        result = use_case.execute(plan)
        self.io.write_note(f"Build {result.build_name!r} completed", "success")

    def _test_menu(self, session: MenuSession) -> int | None:
        actions: tuple[tuple[str, TestAction], ...] = (
            ("Run tests", "run"),
            ("Show test results", "report"),
        )
        selected = self.io.select("Test", [label for label, _ in actions], back_label="Back")
        if selected is None:
            return None
        return self._execute_test(session, actions[selected][1])

    def _execute_test(self, session: MenuSession, action: TestAction) -> None:
        title = "Run tests" if action == "run" else "Show test results"
        group = self._select_source_group(session, "tests", title)
        if group is None:
            return
        names = list(group.names)
        labels = [self._definition_label(group, name) for name in names]
        selected = self.io.select(title, labels, back_label="Back")
        if selected is None:
            return
        use_case = ExecuteTestUseCase(
            self.test_backend_factory(),
            sources=self.sources,
            formatter=self.io.style.render,
        )
        plan = use_case.plan(names[selected], action, self._request(session, group.path))
        for line in describe_test(plan):
            self.io.write_field(line)
        prompt = "Run these tests now?" if action == "run" else "Show test results now?"
        if not self.io.confirm(prompt, default=True):
            self.io.write_note("Test command cancelled.", "muted")
            return
        result = use_case.execute(plan)
        self.io.write_note(
            f"Test {result.test_name!r} {result.action} command completed", "success"
        )

    @staticmethod
    def _is_menu_task(group: SourceFileInfo, name: str) -> bool:
        menu = group.definitions[name].menu
        return menu is not None and menu.enabled

    def _has_menu_tasks(self, session: MenuSession) -> bool:
        return bool(self._source_groups(session, "tasks", requirement=self._is_menu_task))

    def _task_menu(self, session: MenuSession) -> None:
        group = self._select_source_group(session, "tasks", "Tasks", requirement=self._is_menu_task)
        if group is None:
            return
        names = [name for name in group.names if self._is_menu_task(group, name)]
        labels = [
            group.definitions[name].menu.label or self._definition_label(group, name)
            for name in names
        ]
        selected = self.io.select("Tasks", labels, back_label="Back")
        if selected is None:
            return
        task_name = names[selected]
        template = group.definitions[task_name]
        use_case = ExecuteTaskUseCase(
            self.task_backend_factory(),
            sources=self.sources,
            formatter=self.io.style.render,
        )
        plan = use_case.plan(task_name, self._request(session, group.path))
        for line in describe_task(plan):
            self.io.write_field(line)
        if template.menu.confirm and not self.io.confirm("Run this task now?", default=True):
            self.io.write_note("Task cancelled.", "muted")
            return
        result = use_case.execute(plan)
        self.io.write_note(f"Task {result.task_name!r} completed", "success")

    def _scene_menu(self, session: MenuSession) -> int | None:
        actions: tuple[tuple[str, Callable[[MenuSession], int | None]], ...] = (
            ("Start scene", self._start_scene),
            ("Stop scene", self._stop_scene),
            ("Down scene", self._down_scene),
        )
        selected = self.io.select("Scene", [label for label, _ in actions], back_label="Back")
        if selected is None:
            return None
        return actions[selected][1](session)

    def _select_scenario(
        self,
        session: MenuSession,
        title: str,
        *,
        compose_only: bool = False,
    ) -> tuple[SourceFileInfo, str, str] | None:
        """Pick source file, scene and profile; a single profile is used as is."""

        requirement = (
            (lambda group, name: group.definitions[name].compose is not None)
            if compose_only
            else None
        )
        group = self._select_source_group(session, "scenarios", title, requirement=requirement)
        if group is None:
            return None
        scene_names = [
            name
            for name in group.names
            if not compose_only or group.definitions[name].compose is not None
        ]
        scene_labels = [self._definition_label(group, name) for name in scene_names]
        selected = self.io.select("Select scene", scene_labels, back_label="Back")
        if selected is None:
            return None
        scene_name = scene_names[selected]
        profile_names = list(group.definitions[scene_name].profiles)
        if len(profile_names) == 1:
            profile_name = profile_names[0]
        else:
            selected = self.io.select("Select profile", profile_names, back_label="Back")
            if selected is None:
                return None
            profile_name = profile_names[selected]
        return group, scene_name, profile_name

    def _start_scene(self, session: MenuSession) -> None:
        selection = self._select_scenario(session, "Start scene")
        if selection is None:
            return
        group, scene_name, profile_name = selection
        plan = PlanScenarioUseCase(sources=self.sources, formatter=self.io.style.render).plan(
            scene_name,
            profile_name,
            self._request(session, group.path),
        )
        for line in describe_scenario(plan):
            self.io.write_field(line)
        if not self.io.confirm("Start this scenario now?", default=True):
            self.io.write_note("Scenario start cancelled.", "muted")
            return
        result = ScenarioService(self.scenario_executor_factory()).start(plan)
        self.io.write_note(
            f"Started scenario {result.scene_name!r} profile {result.profile_name!r}",
            "success",
        )

    def _stop_scene(self, session: MenuSession) -> None:
        selection = self._select_scenario(session, "Stop scene")
        if selection is None:
            return
        group, scene_name, profile_name = selection
        plan = PlanScenarioUseCase(sources=self.sources, formatter=self.io.style.render).plan(
            scene_name,
            profile_name,
            self._request(session, group.path, interactive=False),
            operation="stop",
        )
        for line in describe_scenario_target(plan):
            self.io.write_field(line)
        if not self.io.confirm("Stop this scenario now?", default=True):
            self.io.write_note("Scenario stop cancelled.", "muted")
            return
        result = ScenarioService(self.scenario_executor_factory()).stop(plan)
        role = "muted" if result.detail == "not running" else "success"
        self.io.write_note(f"Scenario {result.scene_name!r}: {result.detail or 'stopped'}", role)

    def _down_scene(self, session: MenuSession) -> int | None:
        selection = self._select_scenario(session, "Down scene", compose_only=True)
        if selection is None:
            self.io.write_note(
                "Unavailable: no Compose-managed scenes configured; use Stop scene instead.",
                "warning",
            )
            return 2
        group, scene_name, profile_name = selection
        plan = PlanScenarioUseCase(sources=self.sources, formatter=self.io.style.render).plan(
            scene_name,
            profile_name,
            self._request(session, group.path, interactive=False),
            operation="down",
        )
        for line in describe_scenario_target(plan):
            self.io.write_field(line)
        if not self.io.confirm(
            "Down this scenario and remove its Compose environment now?", default=True
        ):
            self.io.write_note("Scenario down cancelled.", "muted")
            return None
        result = ScenarioService(self.scenario_executor_factory()).down(plan)
        self.io.write_note(
            f"Scenario {result.scene_name!r}: {result.detail or 'removed'}", "success"
        )
        return None
