# Scenarios

Scenarios start development and debugging processes in Docker containers. Rigyard uses tmux as the only scenario process entry point; supervisord and production deployment orchestration are outside this feature. Containers may already exist or be created from a referenced Docker Compose file.

| Level | Meaning | tmux mapping |
| --- | --- | --- |
| Scenario | One debugging launch unit | Session |
| Instance | One software system in one container | Window |
| Group | One debugging process inside the container | Pane |

## Existing-container mode

```yaml
robot-system:
  description: Robot development stack
  startup:
    mode: sequential
    interval_seconds: 5
  instances:
    robot1:
      description: Primary robot
      container: robot-development
      startup:
        mode: sequential
        interval_seconds: 2
      groups:
        drivers:
          setup: [/opt/ros/humble/setup.bash, install/setup.bash]
          command: [ros2, launch, robot_bringup, drivers.launch.py]
          interpreter: [/bin/bash, -eo, pipefail]
          workdir: /workspace
          environment:
            ROS_DOMAIN_ID: "7"
        navigation:
          script: /workspace/scripts/navigation.sh
          interpreter: [/bin/bash, -eo, pipefail]
  profiles:
    development:
      restart_container: always
      attach: true
      stop_grace_seconds: 5
      mouse: true
      keep_alive: true
```

Without `compose`, every instance must use `container` to name an existing container or ID. A missing container or failed profile lifecycle operation aborts startup; Rigyard never falls back to Compose automatically.

## Compose mode

```yaml
robot-system:
  compose:
    file: deploy/compose.development.yaml
    project_name: robot-system-debug
    wait_timeout_seconds: 60
    environment:
      WORKSPACE: ${WORKSPACE_ROOT}
  instances:
    robot1:
      service: robot
      groups:
        drivers:
          script: /workspace/scripts/drivers.sh
  profiles:
    development:
      attach: true
```

With `compose`, every instance must use `service`, not `container`. A complete `scene start` first
stops the previous tmux session, then runs `docker compose down --remove-orphans` followed by
`docker compose up -d --wait`. This recreates the project containers and networks while preserving
named volumes and images. Rigyard then resolves each service to exactly one container ID through
`docker compose ps -q`. One instance cannot currently target a scaled service.

A partial start selected with `--instance` does not tear down the Compose project because doing so
would interrupt unselected instances. It runs `compose up` for the selected services and joins or
creates the matching tmux windows.

`compose.file` is relative to the root manifest. `compose.environment` is expanded by Rigyard and passed to Compose `config`, `up`, `ps`, and `down`, overriding the same host variable:

```yaml
# Scenario source
compose:
  file: deploy/compose.yaml
  environment:
    WORKSPACE: ${WORKSPACE_ROOT}
```

```yaml
# compose.yaml
services:
  robot:
    volumes:
      - "${WORKSPACE}:/workspace"
```

Dry-run output shows Compose environment names, not values.

## Scenario fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Menu description |
| `compose` | mapping | no | — | Compose lifecycle configuration |
| `startup` | mapping | no | Parallel | Startup policy between instance windows |
| `instances` | mapping | yes | — | At least one instance |
| `profiles` | mapping | yes | — | At least one profile |

## Compose fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `file` | path | yes | — | Compose YAML based on the root manifest |
| `project_name` | string | no | Stable generated value | Compose project name |
| `wait_timeout_seconds` | integer | no | `60` | 1 through 3600 seconds |
| `environment` | string mapping | no | `{}` | Compose interpolation environment |

## Instance fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Instance description |
| `enabled` | boolean | no | `true` | Included by default |
| `container` | string | conditional | — | Existing-container target |
| `service` | string | conditional | — | Compose service target |
| `startup` | mapping | no | Parallel | Startup policy between group panes |
| `groups` | mapping | yes | — | At least one group |

Instance names become tmux window names and must match `[A-Za-z0-9][A-Za-z0-9_-]*`. Dots and colons conflict with tmux target syntax and are rejected during planning.

## Startup ordering

`startup` controls how sibling tmux objects are submitted. At scenario level it applies to
instance windows; at instance level it applies to group panes:

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `mode` | `parallel` or `sequential` | no | `parallel` | Whether to wait between sibling launches |
| `interval_seconds` | integer | no | `0` | Fixed wait from 0 through 3600 seconds |

Mappings retain their YAML declaration order. In `parallel` mode Rigyard submits commands in that
order without an intentional wait, so the processes run concurrently. In `sequential` mode it
waits `interval_seconds` after successfully submitting one item and before submitting the next;
there is no wait after the final item.

For an instance with sequential panes, Rigyard submits every group with its configured pane
interval. After the final pane is submitted, the scenario-level window interval begins. A
successful submission does not mean that the process is ready. Use this fixed-delay policy to
stagger launches, not as a readiness or health check.

## Group fields

Every group must define exactly one of `script` or `command`:

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Group description |
| `enabled` | boolean | no | `true` | Whether to launch the group |
| `script` | string | conditional | — | Script path inside the container |
| `command` | string list | conditional | — | Direct argv |
| `setup` | string list | no | `[]` | Scripts sourced in order before the process |
| `interpreter` | string list | no | `[/bin/sh, -eu]` | Interpreter for setup and script |
| `user` | string | no | Container default | Passed to `docker exec --user` |
| `workdir` | string | no | Container default | Absolute container working directory |
| `environment` | string mapping | no | `{}` | Group environment |

ROS `setup.bash` generally requires Bash and may not tolerate `set -u`. Use an explicit interpreter such as:

```yaml
interpreter: [/bin/bash, -eo, pipefail]
```

## Profile fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `session` | string | no | Stable generated value | tmux session name |
| `attach` | boolean | no | `true` | Attach after startup |
| `stop_grace_seconds` | integer | no | `5` | Wait 0 through 30 seconds after Ctrl+C |
| `restart_container` | enum | no | `always` | Existing-container lifecycle policy |
| `mouse` | boolean | no | `true` | Enable tmux mouse support |
| `keep_alive` | boolean | no | `true` | Leave interactive shells after group exit |

`restart_container` applies only to existing-container mode:

| Value | Behavior |
| --- | --- |
| `always` | Restart a running container or start a stopped one |
| `if_not_running` | Leave a running container unchanged or start a stopped one |
| `never` | Do not change lifecycle; require the container to be running |

## Resolution and selection

Profiles, instance/group enablement, and instance targets resolve first. Process fields resolve only for enabled groups in selected instances. Runtime-capable fields accept [runtime values](../configuration/runtime-values.md), and strings support [templates](../configuration/templates.md).

By default, all enabled instances are selected. Repeat `--instance NAME` to operate on specific windows:

```bash
rigyard scene start robot-system development --instance robot1
rigyard scene stop robot-system development --instance robot1
```

The profile may be omitted when a scenario defines exactly one profile. Scenarios with multiple profiles require an explicit name.

## tmux and keep-alive behavior

Every pane enables `remain-on-exit`. With `keep_alive: true`:

1. When the group process exits, the pane enters an interactive container shell with the same setup sourced.
2. When that container shell exits, the pane enters an interactive host shell.

This preserves output and supports quick command edits and retries. With `keep_alive: false`, the pane becomes dead when the process exits and retains only its output. A process that exits during the startup grace period still counts as a startup failure, and tmux objects remain for diagnosis.

## Lifecycle boundaries

| Command | tmux | Existing container | Compose containers |
| --- | --- | --- | --- |
| `scene start` | Replaces the complete session, or selected windows for `--instance` | Applies restart policy | Full start runs `down --remove-orphans`, then `up -d --wait`; partial start only runs `up` |
| `scene stop` | Stops processes and closes targets | Preserved | Preserved |
| `scene down` | Stops the complete scenario | Not applicable | Runs `compose down --remove-orphans` |

`scene down` is available only for Compose scenarios and operates on the complete Compose project,
so it rejects `--instance`. A complete Compose start is intentionally destructive to old project
containers: if the subsequent `compose up` fails, the previous environment has already been
removed, while any newly created containers remain available for diagnosis. Use `scene down` to
remove them. Named volumes are not removed.

## Commands

```bash
rigyard scene start robot-system development
rigyard scene start robot-system --dry-run --no-attach
rigyard scene status robot-system development
rigyard scene attach robot-system development --instance robot1 --group drivers
rigyard scene logs robot-system development --instance robot1 --group drivers
rigyard scene logs robot-system development --follow
rigyard scene stop robot-system development
rigyard scene down robot-system development
```

`attach` and group-specific `logs` must identify a unique instance; pass `--instance` in multi-instance scenarios. Stopping first sends Ctrl+C, waits for `stop_grace_seconds`, and then closes the target tmux objects.

### Runtime identity

Generated tmux and Compose names share one identity: the absolute manifest path,
source file path, scene name, and profile name. Different profiles and same-named
scenes from different sources therefore have separate runtime resources. Explicit
`session` and `compose.project_name` values remain overrides; choose unique names
when these configurations should run independently.

Generated names changed from the earlier scene-only tmux naming scheme. Stop old
sessions and remove old Compose projects with the previous version before upgrading;
Rigyard does not automatically remove resources with legacy names.

### Recorded runs and control operations

A successful start records its resolved control target under
`.rigyard/runs/` beside the manifest. Records contain the actual session name,
selected instance/group names, Compose project/file/environment, and lifecycle state;
they do not contain group scripts, commands, or group environment values. Records are
atomically replaced with owner-only file permissions. Keep this directory out of Git.

`stop`, `status`, `attach`, `logs`, and `down` first use this record, even if the
Rigyard configuration has since changed or is missing. Pane indexes are discovered
from live tmux group tags rather than cached indexes. Use `--source` and a profile
when more than one recorded run matches. Recorded identity settings take precedence
over new runtime overrides for control operations. Without a record, control planning
falls back to the current configuration, allowing management of pre-existing sessions.

Partial starts merge their instance targets into the existing run record. Lifecycle
mutations are serialized per project; interactive attachment releases that lock.
Failed starts retain a `failed` record and any diagnostic resources preserved by the
executor. Use `stop` to close panes or `down` to remove a Compose environment. `stop`
retains the record so Compose cleanup remains available; successful `down` removes it.
Compose cleanup still requires the recorded Compose file and a working Docker context.

A start cannot reuse session/project names owned by another recorded run. If explicit
runtime names change, stop the existing run first (or use `down` for an existing Compose
project). Directly constructed Python plans without an identity remain unrecorded.
