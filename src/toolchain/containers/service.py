"""Container creation orchestration independent of Docker."""

from .backend import ContainerBackend
from .models import ContainerCreateResult, ContainerRunPlan


class ContainerCreateService:
    def __init__(self, backend: ContainerBackend) -> None:
        self.backend = backend

    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        return self.backend.create(plan)
