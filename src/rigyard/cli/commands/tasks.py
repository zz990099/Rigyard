"""CLI entry point for custom tasks."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.requests import ResolutionRequest
from ...application.tasks import ExecuteTaskUseCase
from ...providers.docker import DockerExecTaskBackend, docker_sources
from ..common import parse_overrides, print_fields, say
from ..task_output import describe_task
from .parameters import add_resolution_arguments


def register_task_commands(commands: Any) -> None:
    task = commands.add_parser("task", help="run configured custom tasks")
    actions = task.add_subparsers(dest="task_action", required=True)
    run = actions.add_parser("run", help="run a configured custom task")
    run.add_argument("task_name", help="task configuration name under tasks")
    run.add_argument("--source", type=Path, help="source file for ambiguous task names")
    run.add_argument("--dry-run", action="store_true", help="show the plan without executing it")
    add_resolution_arguments(run)
    run.set_defaults(handler=_run_task)


def _run_task(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    use_case = ExecuteTaskUseCase(
        DockerExecTaskBackend(),
        sources=docker_sources(),
        formatter=args.style.render,
    )
    plan = use_case.plan(
        args.task_name,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
            input_fn=args.input_fn,
            source_path=args.source,
        ),
    )
    if args.dry_run:
        print_fields(args.style, describe_task(plan), stream=args.output)
        return 0
    result = use_case.execute(plan)
    say(args.style, f"Task {result.task_name!r} completed", stream=args.output)
    return 0
