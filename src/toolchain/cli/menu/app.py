"""Interactive frontend built on application use cases."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...application.containers import CreateContainerUseCase
from ...application.images import BuildImageUseCase
from ...application.parameters import ResolveParametersUseCase, ValidateConfigUseCase
from ...application.requests import BuildImageRequest, ResolutionRequest
from ...errors import ToolchainError
from ...parameters.context import ResolvedContext
from ...parameters.models import PromptMode, PromptValue
from ...parameters.prompt import prompt_for_value
from ...parameters.resolver import collect_prompts
from ...providers.docker import DockerImageBackend
from ...providers.docker.container_backend import DockerContainerBackend
from ..container_output import describe_container
from .model import MenuAction, MenuRegistry
from .prompt import MenuIO
from .session import MenuSession

BackendFactory = Callable[[], Any]
_CANCEL = object()


class MenuApp:
    def __init__(
        self,
        io: MenuIO | None = None,
        backend_factory: BackendFactory = DockerImageBackend,
        container_backend_factory: BackendFactory = DockerContainerBackend,
    ) -> None:
        self.io = io or MenuIO()
        self.backend_factory = backend_factory
        self.container_backend_factory = container_backend_factory
        self.registry = MenuRegistry(
            (
                MenuAction(
                    "image.build",
                    "Build image",
                    self._build_image,
                    enabled=lambda session: bool(session.config.images),
                    disabled_reason="no images configured",
                ),
                MenuAction("parameters.configure", "Configure parameters", self._configure),
                MenuAction("parameters.show", "Show effective parameters", self._show),
                MenuAction("config.validate", "Validate configuration", self._validate),
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

        while True:
            labels = [self._action_label(action, session) for action in self.registry.actions]
            try:
                selected = self.io.select(
                    f"Toolchain\nConfiguration: {session.config_path}",
                    labels,
                    back_label="Exit",
                )
            except EOFError:
                self.io.write()
                return 0
            except KeyboardInterrupt:
                self.io.write("\nInterrupted")
                return 130
            if selected is None:
                return 0

            action = self.registry.actions[selected]
            if not action.enabled(session):
                self.io.write(f"Unavailable: {action.disabled_reason}")
                continue
            try:
                action.handler(session)
            except KeyboardInterrupt:
                self.io.write("\nCancelled")
            except EOFError:
                self.io.write()
                return 0
            except ToolchainError as exc:
                self.io.write(f"Error: {exc}")

    def _action_label(self, action: MenuAction, session: MenuSession) -> str:
        if action.enabled(session):
            return action.label
        return f"{action.label} [{action.disabled_reason}]"

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
        plan = use_case.plan(names[selected], self._request(session, interactive=True))
        for line in describe_container(plan):
            self.io.write(line)
        if not self.io.confirm("Create and start this container now?"):
            self.io.write("Container creation cancelled.")
            return
        result = use_case.execute(plan)
        self.io.write(f"Created and started {result.container_name} ({result.container_id})")

    def _validate(self, session: MenuSession) -> None:
        session.config = ValidateConfigUseCase().execute(session.config_path)
        self.io.write(f"OK: {session.config_path}")

    def _request(self, session: MenuSession, *, interactive: bool) -> ResolutionRequest:
        return ResolutionRequest(
            config_path=session.config_path,
            values_path=session.values_path,
            overrides=session.overrides,
            interactive=interactive,
            input_fn=self.io.ask,
        )

    def _preview(self, session: MenuSession) -> ResolvedContext:
        return ResolveParametersUseCase().execute(
            self._request(session, interactive=False),
            allow_missing=True,
        )

    def _show(self, session: MenuSession) -> None:
        self._render_parameters(session, self._preview(session))

    def _configure(self, session: MenuSession) -> None:
        while True:
            context = self._preview(session)
            prompts = collect_prompts(session.config)
            names = list(prompts)
            labels = [self._parameter_label(name, session, context) for name in names]
            if session.overrides:
                labels.append("Clear all session overrides")
            selected = self.io.select("Configure parameters", labels, back_label="Back")
            if selected is None:
                return
            if selected == len(names):
                session.overrides.clear()
                self.io.write("Session overrides cleared.")
                continue
            name = names[selected]
            value = self._edit_value(prompts[name])
            if value is _CANCEL:
                continue
            if value is None:
                session.overrides.pop(name, None)
                self.io.write(f"Cleared session override for {name}.")
            else:
                session.overrides[name] = value
                self.io.write(f"{name} = {value!s} [session]")

    def _parameter_label(
        self,
        name: str,
        session: MenuSession,
        context: ResolvedContext,
    ) -> str:
        if name not in context:
            return f"{name} = <unset>"
        source = "session" if name in session.overrides else context.resolved(name).source.value
        return f"{name} = {context[name]!s} [{source}]"

    def _render_parameters(self, session: MenuSession, context: ResolvedContext) -> None:
        self.io.write()
        self.io.write("Effective runtime values")
        for name in collect_prompts(session.config):
            self.io.write(f"- {self._parameter_label(name, session, context)}")

    def _edit_value(self, value: PromptValue) -> Any:
        if value.prompt.mode == PromptMode.SELECT:
            options = list(value.prompt.options or ())
            selected = self.io.select(
                value.prompt.message,
                [str(value) for value in options],
                back_label="Cancel",
            )
            return _CANCEL if selected is None else options[selected]
        if value.prompt.mode == PromptMode.CONFIRM:
            return self.io.confirm(value.prompt.message)
        return prompt_for_value(value, self.io.ask)

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
                overrides=session.overrides,
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
