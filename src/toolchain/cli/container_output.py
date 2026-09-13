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
    for hook in plan.hooks:
        lines.append(
            f"Lifecycle: {hook.phase.value}/{hook.name}; script={hook.script_path}; "
            f"sha256={hook.script_sha256[:12]}; interpreter={hook.interpreter!r}; "
            f"user={hook.user or 'container default'}; "
            f"workdir={hook.workdir or 'container default'}; "
            f"timeout={hook.timeout_seconds}s"
        )
        lines.append(
            "Lifecycle environment keys: "
            + (", ".join(key for key, _ in hook.environment) or "none")
        )
    return tuple(lines)
