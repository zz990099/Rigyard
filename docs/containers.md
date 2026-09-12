# Container creation

`toolchain container create CONFIG NAME` creates **and starts** a new container with
`docker run`. Defaults are interactive stdin, a pseudo-TTY, and detached execution
(`-itd`). Foreground attachment and lifecycle management are not part of this phase.
`detach: false` is rejected rather than exposing an incomplete terminal adapter.

## Architecture

Both CLI and menu call `CreateContainerUseCase`. The application resolves parameters
and snapshots the host environment. `ContainerRunPlanner` consumes those explicit
inputs and produces an immutable plan. `ContainerCreateService` hands the plan to a
backend protocol; only `DockerContainerBackend` constructs Docker arguments.

Configuration contains typed fields, not a shell command or arbitrary extra flags.
The image field is one image reference, and command is an argument list after it.
`${EXTERNAL_TAG}` has no implicit meaning. There is no shell interpolation.
Strings are literal; `{parameter: name}` references the parameter system and
`{env: DISPLAY}` explicitly reads a host environment variable. Missing environment
variables are errors. `{env: NAME, default: value}` permits an explicit fallback.

Bind sources resolve relative to the YAML directory; container paths must be
absolute. Named volumes are distinct from bind mounts. Environment values, device
paths, names and image references are validated before invoking Docker.

`privileged` defaults to false; host networking, host IPC, devices and mounts are
opt-in. The menu shows the resolved name, image and host-access settings before
confirmation, then executes that exact plan. Environment values are not printed.
The CLI supports `--dry-run` to show a redacted plan without contacting Docker.

Name conflicts and Docker failures are reported without deleting, replacing or
restarting existing containers. Success means Docker accepted the detached run,
not that the application is healthy or will remain running. No automatic image
build, `exec`, stop/remove, Compose, post-create scripts or X11 permission changes
are performed. Tests use fake runners and do not start privileged containers.

## Configuration fields

| Field | Docker mapping / default |
|---|---|
| `image` | Required single image reference |
| `name` | `--name`; defaults to the configuration key |
| `interactive`, `tty` | `-i`, `-t`; both default true |
| `detach` | `-d`; only true is currently supported |
| `privileged` | `--privileged`; defaults false |
| `devices` | Repeated `--device` values |
| `group_add` | Repeated `--group-add` values |
| `mounts` | Repeated `--mount`; bind by default, optional volume / read_only |
| `network`, `ipc` | `--network`, `--ipc`; omitted by default |
| `workdir` | `--workdir`; image default when omitted |
| `environment` | Mapping translated to repeated `--env` |
| `command` | Argument list after image; image default when omitted |

Environment values are not a secret store: they are still visible to Docker and
may be visible in host process arguments. Do not place credentials in this model.
Command arguments appear in the plan preview. Bind mounts use `--mount`, which
does not silently create missing source directories like `-v` may do.
X11 socket mounting and DISPLAY do not grant X-server authorization; the user
must configure it separately. USER environment variables do not change the
container's UID, permissions or image-configured user.
