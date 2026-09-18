"""Container creation orchestration independent of Docker."""

from .backend import ContainerBackend
from .models import ContainerCreateResult, ContainerRunPlan


class ContainerCreateService:
    def __init__(self, backend: ContainerBackend) -> None:
        self.backend = backend

    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        created = self.backend.create(plan)
        hooks = tuple(
            self.backend.run_hook(created.container_name, created.container_id, hook)
            for hook in plan.hooks
        )
        return ContainerCreateResult(created.container_name, created.container_id, hooks)
