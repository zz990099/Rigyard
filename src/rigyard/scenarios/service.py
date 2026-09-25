"""Scenario lifecycle boundary with durable control targets and explicit backend ports."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from ..errors import RigyardError, ScenarioPlanError
from .models import ScenarioControlPlan, ScenarioPlan, ScenarioResult, ScenarioTarget
from .ports import ScenarioBackend
from .records import FileRunStore, ScenarioRunRecord, select_recorded_target


def control_target(plan: ScenarioTarget) -> ScenarioControlPlan:
    return ScenarioControlPlan.from_start(plan) if isinstance(plan, ScenarioPlan) else plan


class ScenarioService:
    def __init__(self, executor: ScenarioBackend | None = None) -> None:
        if executor is None:
            from .executor import ScenarioExecutor

            executor = ScenarioExecutor()
        self.executor = executor

    def start(self, plan: ScenarioPlan) -> ScenarioResult:
        if plan.identity is None:
            return self.executor.start(plan)
        store = FileRunStore(plan.identity.config_path)
        target = control_target(plan)
        with store.locked():
            previous = None
            for record in store.records():
                other = record.target
                if other.identity == target.identity:
                    previous = record
                    continue
                if (record.state != "stopped" and other.session == target.session) or (
                    other.compose is not None
                    and target.compose is not None
                    and other.compose.project_name == target.compose.project_name
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
                    raise ScenarioPlanError(
                        "runtime identity changed; stop/down the recorded run first"
                    )
                if plan.partial:
                    if old.session != target.session or old.compose != target.compose:
                        raise ScenarioPlanError(
                            "partial start must use the recorded runtime settings"
                        )
                    merged = {item.name: item for item in old.instances}
                    merged.update({item.name: item for item in target.instances})
                    target = replace(target, instances=tuple(merged.values()))
            target = replace(target, partial=False)
            store.write(ScenarioRunRecord(state="starting", target=target))
            try:
                result = self.executor.start(replace(plan, attach=False))
            except BaseException as failure:
                try:
                    store.write(ScenarioRunRecord(state="failed", target=target))
                except RigyardError as record_error:
                    raise failure from record_error
                raise
            store.write(ScenarioRunRecord(state="running", target=target))
        # Attaching is interactive and must not hold the lifecycle lock.
        if plan.attach:
            self.executor.attach(plan)
        return result

    def stop(self, plan: ScenarioTarget) -> ScenarioResult:
        target = control_target(plan)
        if target.identity is None:
            return self.executor.stop(plan)
        store = FileRunStore(target.identity.config_path)
        with store.locked():
            previous = store.find(
                target.scene_name, target.profile_name, target.identity.source_path
            )
            active = (
                select_recorded_target(
                    previous,
                    [item.name for item in target.instances] if target.partial else None,
                )
                if previous is not None
                else target
            )
            result = self.executor.stop(active)
            if previous is not None:
                state: Literal["running", "stopped"] = "running" if target.partial else "stopped"
                store.write(ScenarioRunRecord(state=state, target=previous.target))
        return result

    def down(self, plan: ScenarioTarget) -> ScenarioResult:
        target = control_target(plan)
        if target.identity is None:
            return self.executor.down(plan)
        store = FileRunStore(target.identity.config_path)
        with store.locked():
            previous = store.find(
                target.scene_name, target.profile_name, target.identity.source_path
            )
            active = replace(previous.target, partial=target.partial) if previous else target
            result = self.executor.down(active)
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
