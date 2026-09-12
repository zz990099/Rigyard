"""One-shot interactive frontend for image builds and container creation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...application.containers import CreateContainerUseCase
from ...application.images import BuildImageUseCase
from ...application.parameters import ValidateConfigUseCase
from ...application.requests import BuildImageRequest, ResolutionRequest
from ...providers.docker import DockerImageBackend
from ...providers.docker.container_backend import DockerContainerBackend
from ..container_output import describe_container
from .model import MenuAction, MenuRegistry
from .prompt import MenuIO
from .session import MenuSession

BackendFactory = Callable[[], Any]


class MenuApp:
    def __init__(
        self,
        io: MenuIO | None = None,
        backend_factory: BackendFactory | None = None,
        container_backend_factory: BackendFactory | None = None,
    ) -> None:
        self.io = io or MenuIO()
        self.backend_factory = backend_factory or DockerImageBackend
        self.container_backend_factory = container_backend_factory or DockerContainerBackend
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
        self.io.write(f"Created and started {result.container_name} ({result.container_id})")

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
        if not self.io.confirm(f"Build {image_name} now?"):
            self.io.write("Build cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Built {result.final_tag} ({len(result.steps)} layer(s))")
