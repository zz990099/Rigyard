"""Redacted container plan rendering shared by terminal frontends."""

from ..containers.models import ContainerRunPlan
from .style import Line, field, line


def describe_container(plan: ContainerRunPlan) -> tuple[Line, ...]:
    lines: list[Line] = [
        field("Container", plan.container_name),
        field("Image", plan.image),
        line(
            ("label", "Interactive"),
            ": ",
            ("value", str(plan.interactive)),
            ("muted", "; TTY: "),
            ("value", str(plan.tty)),
            ("muted", "; detached: True"),
        ),
        field("Privileged", str(plan.privileged)),
        line(
            ("label", "Network"),
            ": ",
            ("value", plan.network or "Docker default"),
            ("muted", "; IPC: "),
            ("value", plan.ipc or "Docker default"),
        ),
        field("Workdir", plan.workdir or "image default"),
    ]
    lines.extend(field("Device", device) for device in plan.devices)
    lines.extend(field("Group", group) for group in plan.group_add)
    lines.extend(
        line(
            ("label", "Mount"),
            ": ",
            ("value", mount.source),
            ("muted", " -> "),
            ("value", mount.target),
            ("muted", f" ({mount.type}, {'ro' if mount.read_only else 'rw'})"),
        )
        for mount in plan.mounts
    )
    lines.append(
        line(
            ("label", "Environment keys"),
            ": ",
            ("muted", ", ".join(key for key, _ in plan.environment) or "none"),
        )
    )
    lines.append(
        field("Command", repr(plan.command) if plan.command else "image default")
    )
    for hook in plan.hooks:
        lines.append(
            line(
                ("label", "Lifecycle"),
                ": ",
                ("value", f"{hook.phase.value}/{hook.name}"),
                (
                    "muted",
                    f"; script={hook.script_path}; sha256={hook.script_sha256[:12]}; "
                    f"interpreter={hook.interpreter!r}; "
                    f"user={hook.user or 'container default'}; "
                    f"workdir={hook.workdir or 'container default'}; "
                    f"timeout={hook.timeout_seconds}s",
                ),
            )
        )
        lines.append(
            line(
                ("label", "Lifecycle environment keys"),
                ": ",
                ("muted", ", ".join(key for key, _ in hook.environment) or "none"),
            )
        )
    return tuple(lines)
