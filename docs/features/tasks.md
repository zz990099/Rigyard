# Custom tasks

Custom tasks provide a controlled extension point for project-specific operations that do not need a dedicated Rigyard feature. Each task executes one user-defined script through `docker exec` inside an existing, running container.

Tasks are always available through the CLI. A task appears under the fixed `Tasks…` interactive-menu entry only when its configuration explicitly enables menu exposure. Task configuration cannot replace built-in menu entries, create nested menus, or execute host commands.

## Configuration

```yaml
clean:
  description: Clean project build artifacts
  container: robot-development
  script: /workspace/scripts/tasks/clean.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: /workspace
  user: root
  tty: auto
  setup:
    - /opt/ros/humble/setup.bash
  environment:
    CLEAN_INSTALL:
      default: "false"
      prompt:
        mode: select
        message: Remove the install directory
        options: ["false", "true"]
  timeout_seconds: 300
  menu:
    enabled: true
    label: Clean workspace
    confirm: true

diagnose:
  description: CLI-only diagnostics
  container: robot-development
  script: /workspace/scripts/tasks/diagnose.sh
```

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | CLI and menu description |
| `container` | string | yes | — | Existing container name or ID |
| `script` | path | yes | — | Script path inside the container |
| `interpreter` | string list | no | `[/bin/sh, -eu]` | Non-empty interpreter argv |
| `workdir` | path | no | Container default | Container working directory |
| `user` | string | no | Container default | Passed to `docker exec --user` |
| `setup` | string list | no | `[]` | Container scripts sourced in order |
| `environment` | string mapping | no | `{}` | Task-only environment overrides |
| `timeout_seconds` | integer | no | unlimited | 1 through 86400 seconds |
| `tty` | `auto`, `always`, or `never` | no | `auto` | Container TTY allocation policy |
| `menu` | mapping | no | CLI only | Fixed Tasks-menu presentation |
| `menu.enabled` | boolean | no | `true` | Show this task when `menu` is present |
| `menu.label` | non-blank string | no | Task name and description | Menu label override |
| `menu.confirm` | boolean | no | `true` | Ask before executing from the menu |

All business fields except menu presentation settings support corresponding [runtime values](../configuration/runtime-values.md). Strings and paths support [templates](../configuration/templates.md). The container, script, interpreter, workdir, and setup files are container-side values.

## Execution semantics

The container must already exist and be running. Rigyard checks its state but does not create, start, or restart it. Setup scripts are sourced in order before the task script is executed. The host never interprets the configured command through an implicit shell.

Task stdout and stderr are streamed unchanged. Rigyard does not parse or persist task output. A non-zero user-command exit status becomes the standard Rigyard execution-backend error.

`tty: auto` allocates a container TTY only when Rigyard's standard output is a terminal. Use `always` to force allocation or `never` to keep output non-interactive.

## Commands

```bash
rigyard task run clean
rigyard task run clean --dry-run
rigyard task run clean --non-interactive \
  --set tasks.clean.environment.CLEAN_INSTALL=true
```

`--dry-run` resolves the task and displays the final `docker exec` argv without checking or invoking Docker. CLI execution does not ask for menu confirmation.

## Scope

Custom tasks intentionally do not provide host commands, multi-step workflows, dependencies, parallel execution, retries, conditions, nested custom menus, or task-to-task calls. Dedicated Rigyard features remain the preferred interface for image, container, build, test, and scenario semantics.
