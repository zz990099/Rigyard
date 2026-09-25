"""Default action catalogue for the interactive menu."""

from __future__ import annotations

from collections.abc import Callable

from .model import MenuAction, MenuRegistry
from .session import MenuSession

MenuHandler = Callable[[MenuSession], int | None]
MenuPredicate = Callable[[MenuSession], bool]


def build_default_registry(
    *,
    build_image: MenuHandler,
    create_container: MenuHandler,
    build_project: MenuHandler,
    scene_menu: MenuHandler,
    test_menu: MenuHandler,
    task_menu: MenuHandler,
    has_menu_tasks: MenuPredicate,
) -> MenuRegistry:
    """Create the stable top-level menu independently from its UI controller."""

    return MenuRegistry(
        (
            MenuAction(
                "image.build",
                "Build image",
                build_image,
                enabled=lambda session: bool(session.config.images),
                disabled_reason="no images configured",
            ),
            MenuAction(
                "container.create",
                "Create container",
                create_container,
                enabled=lambda session: bool(session.config.containers),
                disabled_reason="no containers configured",
            ),
            MenuAction(
                "project.build",
                "Build project",
                build_project,
                enabled=lambda session: bool(session.config.builds),
                disabled_reason="no builds configured",
            ),
            MenuAction(
                "scene.menu",
                "Scene…",
                scene_menu,
                enabled=lambda session: bool(session.config.scenarios),
                disabled_reason="no scenarios configured",
            ),
            MenuAction(
                "test.menu",
                "Test…",
                test_menu,
                enabled=lambda session: bool(session.config.tests),
                disabled_reason="no tests configured",
            ),
            MenuAction(
                "task.menu",
                "Tasks…",
                task_menu,
                enabled=has_menu_tasks,
                disabled_reason="no menu tasks configured",
            ),
        )
    )
