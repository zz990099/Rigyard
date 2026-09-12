"""Redacted container plan rendering shared by terminal frontends."""

from ..containers.models import ContainerRunPlan


def describe_container(plan: ContainerRunPlan) -> tuple[str, ...]:
    lines = [
        f"Container: {plan.container_name}",
        f"Image: {plan.image}",
        f"Interactive: {plan.interactive}; TTY: {plan.tty}; detached: True",
        f"Privileged: {plan.privileged}",
        f"Network: {plan.network or 'Docker default'}; IPC: {plan.ipc or 'Docker default'}",
        f"Workdir: {plan.workdir or 'image default'}",
    ]
    lines.extend(f"Device: {device}" for device in plan.devices)
    lines.extend(f"Group: {group}" for group in plan.group_add)
    lines.extend(
        f"Mount: {mount.source} -> {mount.target} ({mount.type}, "
        f"{'ro' if mount.read_only else 'rw'})"
        for mount in plan.mounts
    )
    lines.append("Environment keys: " + (", ".join(key for key, _ in plan.environment) or "none"))
    lines.append(f"Command: {plan.command!r}" if plan.command else "Command: image default")
    return tuple(lines)
