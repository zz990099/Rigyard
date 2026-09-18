"""One-shot interactive frontend for primary toolchain operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...application.builds import BuildProjectUseCase
from ...application.containers import CreateContainerUseCase
from ...application.images import BuildImageUseCase
from ...application.parameters import ValidateConfigUseCase
from ...application.requests import BuildImageRequest, ResolutionRequest
from ...application.scenarios import PlanScenarioUseCase
from ...config.models import SourceFileInfo
from ...providers.docker import DockerExecBuildBackend, DockerImageBackend
from ...providers.docker.container_backend import DockerContainerBackend
from ...scenarios.executor import ScenarioExecutor
from ...scenarios.service import ScenarioService
from ..build_output import describe_build
from ..container_output import describe_container
from ..scenario_output import describe_scenario, describe_scenario_target
from .model import MenuAction, MenuRegistry
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
        scenario_executor_factory: ScenarioExecutorFactory | None = None,
    ) -> None:
        self.io = io or MenuIO()
        self.backend_factory = backend_factory or DockerImageBackend
        self.container_backend_factory = container_backend_factory or (
            # Replacing an existing container stays an explicit "no" by default.
            lambda: DockerContainerBackend(
                confirm_replace=lambda message: self.io.confirm(message, default=False)
            )
        )
        self.build_backend_factory = build_backend_factory or DockerExecBuildBackend
        self.scenario_executor_factory = scenario_executor_factory or ScenarioExecutor
        self.registry = MenuRegistry(
            (
                MenuAction(
                    "image.build",
                    "Build image",
                    self._build_image,
                    enabled=lambda session: bool(session.config.images),
                    disabled_reason="no images configured",
                ),
                MenuAction(
                    "container.create",
                    "Create container",
                    self._create_container,
                    enabled=lambda session: bool(session.config.containers),
                    disabled_reason="no containers configured",
                ),
                MenuAction(
                    "project.build",
                    "Build project",
                    self._build_project,
                    enabled=lambda session: bool(session.config.builds),
                    disabled_reason="no builds configured",
                ),
                MenuAction(
                    "scene.menu",
                    "Scene…",
                    self._scene_menu,
                    enabled=lambda session: bool(session.config.scenarios),
                    disabled_reason="no scenarios configured",
                ),
            )
        )

    def run(
        self,
        config_path: str | Path = Path("toolchain.yaml"),
        values_path: str | Path | None = None,
    ) -> int:
        config_file = Path(config_path)
        values_file = Path(values_path) if values_path is not None else None
        config = ValidateConfigUseCase().execute(config_file)
        session = MenuSession(config_file, config, values_file)

        try:
            labels = [self._action_label(action, session) for action in self.registry.actions]
            selected = self.io.select(
                f"Toolchain\nProject: {session.config.metadata.name}\n"
                f"Configuration: {session.config_path}",
                labels,
                back_label="Exit",
            )
            if selected is None:
                return 0
            action = self.registry.actions[selected]
            if not action.enabled(session):
                self.io.write(f"Unavailable: {action.disabled_reason}")
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

    def _source_labels(
        self, session: MenuSession, groups: tuple[SourceFileInfo, ...]
    ) -> list[str]:
        labels = []
        for group in groups:
            path = str(self._source_relative_path(session, group.path))
            if group.description:
                label = f"{group.description} ({path})"
            else:
                label = path
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
        use_case = CreateContainerUseCase(self.container_backend_factory())
        plan = use_case.plan(names[selected], self._request(session, group.path))
        for line in describe_container(plan):
            self.io.write(line)
        if not self.io.confirm("Create and start this container now?", default=True):
            self.io.write("Container creation cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(
            f"Created and started {result.container_name} ({result.container_id}); "
            f"completed {len(result.hooks)} lifecycle hook(s)"
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
        use_case = BuildImageUseCase(self.backend_factory())
        plan = use_case.plan(
            BuildImageRequest(
                config_path=session.config_path,
                image_name=image_name,
                values_path=session.values_path,
                interactive=True,
                input_fn=self.io.ask,
                source_path=group.path,
            )
        )
        self.io.write(f"Image: {plan.final_tag}; layers: {len(plan.steps)}")
        if plan.tag_alias is not None:
            self.io.write(f"Alias: {plan.tag_alias}")
        if not self.io.confirm(f"Build {image_name} now?", default=True):
            self.io.write("Build cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Built {result.final_tag} ({len(result.steps)} layer(s))")

    def _build_project(self, session: MenuSession) -> None:
        group = self._select_source_group(session, "builds", "Build project")
        if group is None:
            return
        names = list(group.names)
        labels = [self._definition_label(group, name) for name in names]
        selected = self.io.select("Build project", labels, back_label="Back")
        if selected is None:
            return
        use_case = BuildProjectUseCase(self.build_backend_factory())
        plan = use_case.plan(names[selected], self._request(session, group.path))
        for line in describe_build(plan):
            self.io.write(line)
        if not self.io.confirm("Run this build now?", default=True):
            self.io.write("Build cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Build {result.build_name!r} completed")

    def _scene_menu(self, session: MenuSession) -> int | None:
        actions: tuple[tuple[str, Callable[[MenuSession], int | None]], ...] = (
            ("Start scene", self._start_scene),
            ("Stop scene", self._stop_scene),
            ("Down scene", self._down_scene),
        )
        selected = self.io.select(
            "Scene", [label for label, _ in actions], back_label="Back"
        )
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
        group = self._select_source_group(
            session, "scenarios", title, requirement=requirement
        )
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
        plan = PlanScenarioUseCase().plan(
            scene_name,
            profile_name,
            self._request(session, group.path),
        )
        for line in describe_scenario(plan):
            self.io.write(line)
        if not self.io.confirm("Start this scenario now?", default=True):
            self.io.write("Scenario start cancelled.")
            return
        result = ScenarioService(self.scenario_executor_factory()).start(plan)
        self.io.write(f"Started scenario {result.scene_name!r} profile {result.profile_name!r}")

    def _stop_scene(self, session: MenuSession) -> None:
        selection = self._select_scenario(session, "Stop scene")
        if selection is None:
            return
        group, scene_name, profile_name = selection
        plan = PlanScenarioUseCase().plan(
            scene_name,
            profile_name,
            self._request(session, group.path, interactive=False),
            resolve_group_runtime=False,
        )
        for line in describe_scenario_target(plan):
            self.io.write(line)
        if not self.io.confirm("Stop this scenario now?", default=True):
            self.io.write("Scenario stop cancelled.")
            return
        result = ScenarioService(self.scenario_executor_factory()).stop(plan)
        self.io.write(f"Scenario {result.scene_name!r}: {result.detail or 'stopped'}")

    def _down_scene(self, session: MenuSession) -> int | None:
        selection = self._select_scenario(session, "Down scene", compose_only=True)
        if selection is None:
            self.io.write(
                "Unavailable: no Compose-managed scenes configured; use Stop scene instead."
            )
            return 2
        group, scene_name, profile_name = selection
        plan = PlanScenarioUseCase().plan(
            scene_name,
            profile_name,
            self._request(session, group.path, interactive=False),
            resolve_group_runtime=False,
        )
        for line in describe_scenario_target(plan):
            self.io.write(line)
        if not self.io.confirm(
            "Down this scenario and remove its Compose environment now?", default=True
        ):
            self.io.write("Scenario down cancelled.")
            return None
        result = ScenarioService(self.scenario_executor_factory()).down(plan)
        self.io.write(f"Scenario {result.scene_name!r}: {result.detail or 'removed'}")
        return None
