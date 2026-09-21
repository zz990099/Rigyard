# Project builds

Project builds run through `docker exec` inside an existing container. Rigyard can start a stopped
container but does not create, recreate, restart, stop, or pull it, and does not interpret build
systems such as colcon, catkin, or CMake.

## Configuration

```yaml
native:
  description: Native container build
  container: robot-development
  start_container: true
  script: ${CONTAINER_WORKSPACE_ROOT}/scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: ${CONTAINER_WORKSPACE_ROOT}
  user: root
  tty: auto
  setup:
    - /opt/ros/humble/setup.bash
    - install/setup.bash
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Select build type
        options: [Debug, Release, RelWithDebInfo]
  timeout_seconds: 3600
```

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Menu description |
| `container` | string | yes | — | Existing container name or ID |
| `start_container` | boolean | no | `true` | Start the container when it is stopped |
| `script` | path | yes | — | Script path inside the container |
| `interpreter` | string list | no | `[/bin/sh, -eu]` | Non-empty container interpreter argv |
| `workdir` | path | no | Container default | Container working directory |
| `user` | string | no | Container default | Passed to `docker exec --user` |
| `tty` | `auto`, `always`, or `never` | no | `auto` | Container TTY allocation policy |
| `setup` | string list | no | `[]` | Container scripts sourced in order |
| `environment` | string mapping | no | `{}` | Build-only environment; host environment is not inherited |
| `timeout_seconds` | integer | no | unlimited | 1 through 86400 seconds |

All business fields support corresponding [runtime values](../configuration/runtime-values.md). Strings and paths support [templates](../configuration/templates.md). The `container` field is commonly paired with the `docker-containers` dynamic option source.

## Execution semantics

The container must already exist. By default, Rigyard leaves a running container unchanged and
runs `docker start` when it is stopped. Set `start_container: false` to require an already-running
container without changing its lifecycle. A missing container is always an error, and Rigyard does
not create, recreate, restart, or stop the container. After an automatic start, Rigyard verifies
that the container remained running before it invokes `docker exec`.

Automatic starts operate on the selected container name or ID and do not run lifecycle
`post_start` hooks from a container definition.

Container-side control flow is equivalent to:

```text
. /opt/ros/humble/setup.bash &&
. install/setup.bash &&
exec /bin/bash -euo pipefail /workspace/scripts/build-native.sh
```

The interpreter, setup scripts, build script, and workdir are container-side values. Rigyard invokes `docker exec` through argv and never asks the host shell to interpret the business command. Only explicitly configured environment overrides are passed.

`tty: auto` adds `docker exec --tty` when Rigyard's standard output is connected to a terminal. This enables dynamic progress displays such as colcon's status line while keeping redirected output and CI logs free of terminal control characters. Use `always` to force TTY allocation or `never` to disable it.

`timeout_seconds` controls the host-side `docker exec` client and cannot guarantee termination of every process spawned inside the container. For strict process-tree timeout behavior, use a container-side mechanism such as `timeout` in the build script.

## Commands

```bash
rigyard build native
rigyard build native --dry-run
rigyard build native --source config/builds.yaml
rigyard build native --non-interactive \
  --set builds.native.environment.BUILD_TYPE=Debug
```

`--dry-run` resolves the container start policy, script, setup, environment, and final `docker exec`
argv without checking or invoking Docker.
