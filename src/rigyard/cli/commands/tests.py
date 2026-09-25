"""CLI entry points for user-defined test commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...application.requests import ResolutionRequest
from ...application.tests import ExecuteTestUseCase
from ...providers.docker import DockerExecTestBackend, docker_sources
from ...tests.models import TestAction
from ..common import parse_overrides, print_fields, say
from ..test_output import describe_test
from .parameters import add_resolution_arguments


def register_test_commands(commands: Any) -> None:
    test = commands.add_parser("test", help="run configured test commands")
    actions = test.add_subparsers(dest="test_action", required=True)
    for action, help_text in (
        ("run", "run configured test cases"),
        ("report", "run the configured test results command"),
    ):
        command = actions.add_parser(action, help=help_text)
        command.add_argument("test_name", help="test configuration name under tests")
        command.add_argument("--source", type=Path, help="source file for ambiguous test names")
        command.add_argument(
            "--dry-run", action="store_true", help="show the plan without executing it"
        )
        add_resolution_arguments(command)
        command.set_defaults(handler=_test)


def _test(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        overrides = parse_overrides(args.sets)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    action: TestAction = args.test_action
    use_case = ExecuteTestUseCase(
        DockerExecTestBackend(),
        sources=docker_sources(),
        formatter=args.style.render,
    )
    plan = use_case.plan(
        args.test_name,
        action,
        ResolutionRequest(
            config_path=args.config_path,
            values_path=args.values,
            overrides=overrides,
            interactive=not args.non_interactive,
            input_fn=args.input_fn,
            source_path=args.source,
            workspace_root=args.workspace_root,
        ),
    )
    if args.dry_run:
        print_fields(args.style, describe_test(plan), stream=args.output)
        return 0
    result = use_case.execute(plan)
    say(
        args.style,
        f"Test {result.test_name!r} {result.action} command completed",
        stream=args.output,
    )
    return 0
