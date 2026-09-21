# Tests

Tests are user-defined commands executed through `docker exec` inside an existing container.
Rigyard can start the container when necessary. Each test target has two independent actions:

- `run` executes the configured test cases.
- `report` executes the configured result or log command.

Rigyard does not depend on colcon, pytest, CTest, or any other test framework. It does not capture, parse, normalize, persist, or interpret test output. Both commands stream their stdout and stderr unchanged, and the user-provided process exit code determines success or failure.

## Configuration

```yaml
unit:
  description: Unit tests
  container: robot-development
  start_container: true
  workdir: /workspace
  user: root
  tty: auto
  setup:
    - /opt/ros/humble/setup.bash
    - install/setup.bash
  environment:
    TEST_JOBS:
      default: "4"
      prompt:
        mode: input
        message: Enter parallel test jobs
  run:
    script: /workspace/scripts/tests/run-unit.sh
    interpreter: [/bin/bash, -euo, pipefail]
    timeout_seconds: 1800
  report:
    script: /workspace/scripts/tests/show-unit-results.sh
    interpreter: [/bin/bash, -euo, pipefail]
    timeout_seconds: 60
```

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Menu description |
| `container` | string | yes | — | Existing container name or ID |
| `start_container` | boolean | no | `true` | Start the container when it is stopped |
| `workdir` | path | no | Container default | Container working directory |
| `user` | string | no | Container default | Passed to `docker exec --user` |
| `tty` | `auto`, `always`, or `never` | no | `auto` | Container TTY allocation policy |
| `setup` | string list | no | `[]` | Container scripts sourced in order |
| `environment` | string mapping | no | `{}` | Environment passed to both actions |
| `run` | action | yes | — | Test execution command |
| `report` | action | yes | — | Result and log output command |
| `run.script`, `report.script` | path | yes | — | Script path inside the container |
| `run.interpreter`, `report.interpreter` | string list | no | `[/bin/sh, -eu]` | Non-empty interpreter argv |
| `run.timeout_seconds`, `report.timeout_seconds` | integer | no | unlimited | 1 through 86400 seconds |

All business fields support corresponding [runtime values](../configuration/runtime-values.md). Strings and paths support [templates](../configuration/templates.md). The container, workdir, setup files, action scripts, and interpreters are container-side values.

## Execution semantics

The container must already exist. By default, Rigyard leaves a running container unchanged and
runs `docker start` when it is stopped. Set `start_container: false` to require an already-running
container. Rigyard does not create, recreate, restart, or stop the container. An automatically
started container must remain running before execution continues. Setup scripts are sourced in
order before the selected action script is executed. The host never interprets the configured
command through an implicit shell.

Automatic starts operate on the selected container name or ID and do not run lifecycle
`post_start` hooks from a container definition.

The report command has no special output contract. It can run `colcon test-result --verbose`, print a pytest summary, display logs, calculate coverage, or invoke any project-specific reporter. Rigyard streams that output exactly as produced.

`tty: auto` allocates a container TTY only when Rigyard's standard output is a terminal. Use `always` to force allocation or `never` to keep output non-interactive.

## Commands

```bash
rigyard test run unit
rigyard test report unit
rigyard test run unit --dry-run
rigyard test report unit --dry-run
rigyard test run unit --non-interactive \
  --set tests.unit.environment.TEST_JOBS=8
```

`--dry-run` resolves the configuration and container start policy and displays the final
`docker exec` argv without checking or invoking Docker.
