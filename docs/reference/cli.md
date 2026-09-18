# CLI reference

## Global entry point

```text
toolchain [--version] [-f PATH] [--values PATH] [--color MODE] COMMAND
```

| Option | Description |
| --- | --- |
| `--version` | Print the installed version |
| `-f, --config PATH` | Select the root manifest and override workspace initialization |
| `--values PATH` | Runtime values file used by the interactive menu |
| `--color auto\|always\|never` | Output color mode; default is `auto` |

With no command, Toolchain opens the one-shot interactive menu. When stdin is not a terminal, it prints help and returns 2.

## Configuration commands

```bash
toolchain validate
toolchain inspect [--format json|yaml]
toolchain resolve [--values FILE] [--set PATH=VALUE] \
  [--non-interactive] [--with-sources] [--format json|yaml]
```

- `validate` checks all configuration and template syntax.
- `inspect` lists inline runtime parameters.
- `resolve` resolves all runtime parameters; `--with-sources` includes value origins.

## Feature commands

```bash
toolchain image build NAME [resolution options]
toolchain container create NAME [--dry-run] [resolution options]
toolchain build NAME [--dry-run] [resolution options]
toolchain scene ACTION SCENE [PROFILE] [scene options] [resolution options]
```

Common resolution options:

| Option | Description |
| --- | --- |
| `--source PATH` | Select a source when duplicate names exist |
| `--values PATH` | Values YAML for this operation |
| `--set PATH=VALUE` | Override one runtime value; repeatable |
| `--non-interactive` | Disable prompts and fail on missing values |

`image build` executes directly and currently has no `--dry-run`. Container creation, project builds, and scenario start support plan previews.

Scenario actions:

| Action | Additional options |
| --- | --- |
| `start` | `--instance NAME`, `--dry-run`, `--replace`, `--no-attach` |
| `stop` | `--instance NAME` |
| `down` | Compose scenarios only; rejects `--instance` |
| `status` | `--instance NAME` |
| `attach` | `--instance NAME`, `--group GROUP` |
| `logs` | `--instance NAME`, `--group GROUP`, `--follow` |

`--instance` is repeatable. Use `toolchain COMMAND --help` for the exact parser surface.

## Workspace initialization

```bash
toolchain init -f PATH [--force] [--alias NAME]
```

The command validates the configuration and writes `.toolchain/context.yaml` in the current directory. Resolution order is explicit `--config`, current-directory binding, then current-directory `toolchain.yaml`. Parent directories are not searched.

When the manifest is inside the workspace, the binding records a relative path so the same checkout can use different host and container mount roots. Rebinding the same configuration is idempotent; changing it requires `--force`.

`--alias NAME` creates an executable wrapper in the workspace root:

```bash
toolchain init -f src/robot/.toolchain/toolchain.yaml --alias robot
./robot build native
```

The wrapper locates the bound configuration relative to itself and invokes the stable `toolchain --config ...` entry point. It does not modify PATH or write to a user-wide bin directory. Existing files are protected unless `--force` explicitly replaces them.

## Interactive menu

The menu offers Build image, Create container, Build project, and Scene actions for Start, Stop, and Down. The process exits after one successful, failed, or cancelled action. Menu and direct CLI paths use the same application use cases.

Plan confirmation defaults to `[Y/n]`. Removing and recreating an existing container is the only confirmation that defaults to `[y/N]`.

## Output color

`--color=auto` uses color only when the output stream is a terminal. `NO_COLOR`, `TERM=dumb`, and `--color=never` disable it for CI and redirected logs.
