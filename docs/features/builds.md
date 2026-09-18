# Project builds

Project builds always run through `docker exec` inside an existing, running container. Rigyard does not create, start, or pull the build container and does not interpret build systems such as colcon, catkin, or CMake.

## Configuration

```yaml
native:
  description: Native container build
  container: robot-development
  script: ${CONTAINER_WORKSPACE_ROOT}/scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: ${CONTAINER_WORKSPACE_ROOT}
  user: root
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
| `script` | path | yes | — | Script path inside the container |
| `interpreter` | string list | no | `[/bin/sh, -eu]` | Non-empty container interpreter argv |
| `workdir` | path | no | Container default | Container working directory |
| `user` | string | no | Container default | Passed to `docker exec --user` |
| `setup` | string list | no | `[]` | Container scripts sourced in order |
| `environment` | string mapping | no | `{}` | Build-only environment; host environment is not inherited |
| `timeout_seconds` | integer | no | unlimited | 1 through 86400 seconds |

All business fields support corresponding [runtime values](../configuration/runtime-values.md). Strings and paths support [templates](../configuration/templates.md). The `container` field is commonly paired with the `docker-containers` dynamic option source.

## Execution semantics

The container must exist and be running. A missing or stopped container causes an error without changing its lifecycle. Container-side control flow is equivalent to:

```text
. /opt/ros/humble/setup.bash &&
. install/setup.bash &&
exec /bin/bash -euo pipefail /workspace/scripts/build-native.sh
```

The interpreter, setup scripts, build script, and workdir are container-side values. Rigyard invokes `docker exec` through argv and never asks the host shell to interpret the business command. Only explicitly configured environment overrides are passed.

`timeout_seconds` controls the host-side `docker exec` client and cannot guarantee termination of every process spawned inside the container. For strict process-tree timeout behavior, use a container-side mechanism such as `timeout` in the build script.

## Commands

```bash
rigyard build native
rigyard build native --dry-run
rigyard build native --source config/builds.yaml
rigyard build native --non-interactive \
  --set builds.native.environment.BUILD_TYPE=Debug
```

`--dry-run` resolves the container, script, setup, environment, and final `docker exec` argv without checking or invoking the Docker container.
