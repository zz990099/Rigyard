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
from ...providers.docker import DockerImageBackend
from ...providers.docker.container_backend import DockerContainerBackend
from ...providers.host import HostBuildBackend
from ...scenarios.executor import ScenarioExecutor
from ...scenarios.service import ScenarioService
from ..build_output import describe_build
from ..container_output import describe_container
from ..scenario_output import describe_scenario
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
            lambda: DockerContainerBackend(confirm_replace=self.io.confirm)
        )
        self.build_backend_factory = build_backend_factory or HostBuildBackend
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
                    "scene.start",
                    "Start scene",
                    self._start_scene,
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
            action.handler(session)
            return 0
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

    def _request(self, session: MenuSession) -> ResolutionRequest:
        return ResolutionRequest(
            config_path=session.config_path,
            values_path=session.values_path,
            interactive=True,
            input_fn=self.io.ask,
        )

    def _create_container(self, session: MenuSession) -> None:
        names = list(session.config.containers)
        labels = [
            f"{name} — {session.config.containers[name].description}"
            if session.config.containers[name].description
            else name
            for name in names
        ]
        selected = self.io.select("Create container", labels, back_label="Back")
        if selected is None:
            return
        use_case = CreateContainerUseCase(self.container_backend_factory())
        plan = use_case.plan(names[selected], self._request(session))
        for line in describe_container(plan):
            self.io.write(line)
        if not self.io.confirm("Create and start this container now?"):
            self.io.write("Container creation cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(
            f"Created and started {result.container_name} ({result.container_id}); "
            f"completed {len(result.hooks)} lifecycle hook(s)"
        )

    def _build_image(self, session: MenuSession) -> None:
        image_names = list(session.config.images)
        labels = []
        for name in image_names:
            description = session.config.images[name].description
            labels.append(f"{name} — {description}" if description else name)
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
            )
        )
        self.io.write(f"Image: {plan.final_tag}; layers: {len(plan.steps)}")
        if plan.tag_alias is not None:
            self.io.write(f"Alias: {plan.tag_alias}")
        if not self.io.confirm(f"Build {image_name} now?"):
            self.io.write("Build cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Built {result.final_tag} ({len(result.steps)} layer(s))")

    def _build_project(self, session: MenuSession) -> None:
        names = list(session.config.builds)
        labels = [
            f"{name} — {session.config.builds[name].description}"
            if session.config.builds[name].description
            else name
            for name in names
        ]
        selected = self.io.select("Build project", labels, back_label="Back")
        if selected is None:
            return
        use_case = BuildProjectUseCase(self.build_backend_factory())
        plan = use_case.plan(names[selected], self._request(session))
        for line in describe_build(plan):
            self.io.write(line)
        if not self.io.confirm("Run this build now?"):
            self.io.write("Build cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Build {result.build_name!r} completed")

    def _start_scene(self, session: MenuSession) -> None:
        scene_names = list(session.config.scenarios)
        scene_labels = [
            f"{name} — {session.config.scenarios[name].description}"
            if session.config.scenarios[name].description
            else name
            for name in scene_names
        ]
        selected = self.io.select("Start scene", scene_labels, back_label="Back")
        if selected is None:
            return
        scene_name = scene_names[selected]
        profile_names = list(session.config.scenarios[scene_name].profiles)
        selected = self.io.select("Select profile", profile_names, back_label="Back")
        if selected is None:
            return
        profile_name = profile_names[selected]
        plan = PlanScenarioUseCase().plan(
            scene_name,
            profile_name,
            self._request(session),
        )
        for line in describe_scenario(plan):
            self.io.write(line)
        if not self.io.confirm("Start this scenario now?"):
            self.io.write("Scenario start cancelled.")
            return
        result = ScenarioService(self.scenario_executor_factory()).start(plan)
        self.io.write(f"Started scenario {result.scene_name!r} profile {result.profile_name!r}")
