"""Scenario lifecycle boundary with durable control targets and explicit backend ports."""

from __future__ import annotations

from dataclasses import replace

from ..errors import RigyardError, ScenarioPlanError
from .models import ScenarioControlPlan, ScenarioPlan, ScenarioResult, ScenarioTarget
from .ports import ScenarioBackend
from .records import FileRunStore, ScenarioRunRecord, select_recorded_target, system_boot_id


def control_target(plan: ScenarioTarget) -> ScenarioControlPlan:
    return ScenarioControlPlan.from_start(plan) if isinstance(plan, ScenarioPlan) else plan


class ScenarioService:
    def __init__(
        self, executor: ScenarioBackend | None = None, *, owner_unit: str | None = None
    ) -> None:
        self.owner_unit = owner_unit
        if executor is None:
            from .executor import ScenarioExecutor

            executor = ScenarioExecutor()
        self.executor = executor

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        if plan.identity is None:
            return self.executor.start(plan)
        if plan.owner_unit != self.owner_unit:
            raise ScenarioPlanError("scenario service owner mismatch")
        store = FileRunStore(plan.identity.config_path)
        target = control_target(plan)
        boot_id = system_boot_id()
        with store.locked():
            previous = None
            for record in store.records():
                other = record.target
                if (other.owner_unit or target.owner_unit) and (
                    boot_id and record.boot_id and boot_id != record.boot_id
                ):
                    continue
                if other.identity == target.identity:
                    if record.state != "stopped" and (
                        other.owner_unit != target.owner_unit
                        or other.tmux_socket != target.tmux_socket
                    ):
                        raise ScenarioPlanError("scenario has another owner; stop it first")
                    previous = record
                    continue
                if (
                    (
                        record.state != "stopped"
                        and other.session == target.session
                        and other.tmux_socket == target.tmux_socket
                    )
                    or (
                        (other.owner_unit or target.owner_unit)
                        and record.state != "stopped"
                        and {i.container for i in other.instances if i.container}
                        & {i.container for i in target.instances if i.container}
                    )
                    or (
                        other.compose is not None
                        and target.compose is not None
                        and other.compose.project_name == target.compose.project_name
                    )
                ):
                    raise ScenarioPlanError("runtime resources belong to another recorded scenario")
            if previous is not None:
                old = previous.target
                if (old.session != target.session and previous.state != "stopped") or (
                    old.compose is not None
                    and (
                        target.compose is None
                        or old.compose.project_name != target.compose.project_name
                    )
                ):
                    raise ScenarioPlanError("runtime identity changed; stop the recorded run first")
                if plan.partial:
                    if old.session != target.session or old.compose != target.compose:
                        raise ScenarioPlanError(
                            "partial start must use the recorded runtime settings"
                        )
                    merged = {item.name: item for item in old.instances}
                    merged.update({item.name: item for item in target.instances})
                    target = replace(target, instances=tuple(merged.values()))
            target = replace(target, partial=False)
            store.write(ScenarioRunRecord(boot_id=boot_id, state="starting", target=target))
            try:
                result = self.executor.start(replace(plan, attach=False))
            except BaseException as failure:
                try:
                    store.write(ScenarioRunRecord(boot_id=boot_id, state="failed", target=target))
                except RigyardError as record_error:
                    raise failure from record_error
                raise
            store.write(ScenarioRunRecord(boot_id=boot_id, state="running", target=target))
        # Attaching is interactive and must not hold the lifecycle lock.
        if plan.attach:
            self.executor.attach(plan)
        return result

    def stop(self, plan: ScenarioTarget) -> ScenarioResult:
        target = control_target(plan)
        if target.partial:
            raise ScenarioPlanError("scene stop does not support partial instance selection")
        if target.identity is None:
            return self.executor.stop(plan)
        store = FileRunStore(target.identity.config_path)
        previous = store.find(target.scene_name, target.profile_name, target.identity.source_path)
        if previous is not None and previous.target.owner_unit != self.owner_unit:
            if previous.target.owner_unit is None:
                raise ScenarioPlanError("scenario belongs to a manual run")
            from ..autostart.systemd import SystemdManager

            SystemdManager().stop(previous.target.owner_unit)
            return ScenarioResult(target.scene_name, target.profile_name, "stopped")
        with store.locked():
            previous = store.find(
                target.scene_name, target.profile_name, target.identity.source_path
            )
            active = select_recorded_target(previous, None) if previous is not None else target
            if active.owner_unit != self.owner_unit:
                raise ScenarioPlanError("scenario owner changed; retry stop")
            result = self.executor.stop(active)
            store.remove(target)
        return result

    def status(self, plan: ScenarioTarget) -> ScenarioResult:
        return self.executor.status(plan)

    def attach(
        self,
        plan: ScenarioTarget,
        instance_name: str | None = None,
        group_name: str | None = None,
    ) -> ScenarioResult:
        return self.executor.attach(plan, instance_name, group_name)

    def logs(
        self,
        plan: ScenarioTarget,
        instance_name: str | None = None,
        group_name: str | None = None,
        *,
        follow: bool = False,
    ) -> ScenarioResult:
        return self.executor.logs(plan, instance_name, group_name, follow=follow)
