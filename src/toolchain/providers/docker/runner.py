"""Backward-compatible imports for the shared process runner."""

from ...execution.runner import CommandResult, CommandRunner, SubprocessRunner

__all__ = ["CommandResult", "CommandRunner", "SubprocessRunner"]
