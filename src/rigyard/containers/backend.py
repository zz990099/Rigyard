"""Container execution port."""

from typing import Protocol

from .models import ContainerCreateResult, ContainerHookPlan, ContainerHookResult, ContainerRunPlan


class ContainerBackend(Protocol):
    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        """Create and start a container from a fully resolved plan."""

    def run_hook(
        self,
        container_name: str,
        container_id: str,
        hook: ContainerHookPlan,
    ) -> ContainerHookResult:
        """Run one lifecycle hook in an already running container."""
