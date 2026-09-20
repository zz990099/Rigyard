# Containers

The container feature converts a named definition into an explicit `docker run` plan and can execute lifecycle hooks inside a newly created container.

## Configuration

```yaml
development:
  description: Interactive robot development container
  name: robot-development
  image: example/robot-development:latest
  interactive: true
  tty: true
  detach: true
  privileged: false
  devices: [/dev/dri]
  group_add: [video]
  network: host
  ipc: host
  mounts:
    - /tmp/.X11-unix:/tmp/.X11-unix
    - ../:/workspace
    - cache:/cache:ro
  workdir: /workspace
  environment:
    DISPLAY: {env: DISPLAY}
    USER: {env: USER}
    MODE: development
  command: [/bin/bash]
```

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Menu description |
| `image` | string | yes | — | Docker image reference |
| `name` | string | no | Definition key | Container name |
| `interactive` | boolean | no | `true` | Adds `docker run -i` |
| `tty` | boolean | no | `true` | Adds `docker run -t` |
| `detach` | boolean | no | `true` | Must currently remain `true` |
| `privileged` | boolean | no | `false` | Enables privileged mode |
| `devices` | string list | no | `[]` | `/host[:/container[:rwm]]` entries |
| `group_add` | string list | no | `[]` | Additional container groups |
| `mounts` | string list | no | `[]` | Bind mounts or named volumes |
| `network` | string | no | — | Docker network mode or name |
| `ipc` | string | no | — | Docker IPC mode |
| `workdir` | string | no | — | Absolute container working directory |
| `environment` | mapping | no | `{}` | Container environment |
| `lifecycle` | mapping | no | empty | Post-creation hooks |
| `command` | string list | no | `[]` | Container command argv |

Business fields support corresponding [runtime values](../configuration/runtime-values.md), except for `description`, `detach`, and lifecycle structure names. Strings support [templates](../configuration/templates.md).

## Mounts

Each mount uses `SOURCE:TARGET[:ro|rw]`:

- `/absolute:/target`, `../relative:/target`, and `~/home:/target` are bind mounts.
- `cache:/target` is a named volume.
- Relative bind sources are based on the root manifest directory.
- Targets must be absolute container paths and cannot repeat.
- The mode defaults to `rw` and may only be `ro` or `rw`.

Replacement input is supported and remains the default behavior:

```yaml
mounts:
  default: ["../:/workspace"]
  prompt:
    mode: input
    repeat: true
    message: Enter a mount
    item_hint: SOURCE:TARGET[:ro]
```

Use `base` with `merge: append` when some mounts must always remain while the user supplies additions:

```yaml
mounts:
  base:
    - ${PROJECT_ROOT}:/workspace
  default: ~/sysroots/aarch64
  prompt:
    mode: input
    merge: append
    message: Enter the AArch64 sysroot directory
    input_template: "${INPUT}:/opt/sysroots/aarch64"
```

The input template is applied to each selected item. Set `repeat: true` with a list-valued default to append multiple mounts. See [Input composition](../configuration/runtime-values.md#input-composition).

## Environment

Use fixed values or templates:

```yaml
environment:
  MODE: development
  RUN_ID: ${utcdate:%Y%m%dT%H%M%SZ}
```

Container and hook environments also support structured host references:

```yaml
environment:
  DISPLAY: {env: DISPLAY}
  OPTIONAL_TOKEN: {env: TOKEN, default: ""}
```

Planning fails when a referenced host variable has no default and is missing. Structured values are included in Docker error redaction. See [Two forms of environment lookup](../configuration/templates.md#two-forms-of-environment-lookup).

## Lifecycle hooks

```yaml
cross-aarch64:
  name:
    default: robot-cross-aarch64
    prompt:
      mode: input
      message: Enter the cross-compilation container prefix
      input_template: "${INPUT}_dev"
  image: example/cross-aarch64-base:latest
  mounts:
    base:
      - ${PROJECT_ROOT}:/workspace
    default: ~/sysroots/aarch64
    prompt:
      mode: input
      merge: append
      message: Enter the AArch64 sysroot directory
      input_template: "${INPUT}:/opt/sysroots/aarch64"
  workdir: /workspace
  lifecycle:
    post_create:
      - name: prepare-sysroot
        script: scripts/cross/prepare-sysroot.sh
        interpreter: [/bin/bash, -eu]
        user: root
        workdir: /workspace
        environment:
          SYSROOT: /opt/sysroots/aarch64
        timeout_seconds: 300
    post_start:
      - name: verify-rigyard
        script: scripts/cross/verify-rigyard.sh
        timeout_seconds: 30
  command: [/bin/bash]
```

Execution order is fixed:

```text
docker run → post_create in declaration order → post_start in declaration order
```

| Hook field | Required | Default | Rule |
| --- | ---: | --- | --- |
| `name` | yes | — | Unique within its phase |
| `script` | yes | — | Non-empty UTF-8 host file, relative to the manifest, at most 1 MiB |
| `interpreter` | no | `[/bin/sh, -eu]` | Non-empty container argv |
| `user` | no | — | Passed to `docker exec --user` |
| `workdir` | no | — | Absolute container path |
| `environment` | no | `{}` | Injected only into this hook |
| `timeout_seconds` | no | `300` | 1 through 86400 seconds |

Script content is sent to the container interpreter through `docker exec -i` stdin. It need not be mounted into the container and never passes through a host shell. A failed hook returns an execution error but leaves the created container available for diagnosis. Hooks should be idempotent.

## Existing names

If a container with the requested name exists, interactive mode asks whether to remove it with `docker rm -f` and recreate it. The default answer is no. Refusal, or a name collision in non-interactive mode, cancels creation. Removing the container does not delete mounted volumes.

## Commands

```bash
rigyard container create development
rigyard container create development --dry-run
rigyard container create development --source config/containers.yaml
```

`--dry-run` resolves parameters, host environment values, mounts, and hook scripts without invoking Docker.
