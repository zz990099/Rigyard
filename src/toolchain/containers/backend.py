"""Container execution port."""

from typing import Protocol

from .models import ContainerCreateResult, ContainerRunPlan


class ContainerBackend(Protocol):
    def create(self, plan: ContainerRunPlan) -> ContainerCreateResult:
        """Create and start a container from a fully resolved plan."""
