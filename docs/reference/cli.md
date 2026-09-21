# CLI reference

## Global entry point

```text
rigyard [--version] [-f PATH] [--values PATH] [--color MODE] COMMAND
```

| Option | Description |
| --- | --- |
| `--version` | Print the installed version |
| `-f, --config PATH` | Select the root manifest and override workspace initialization |
| `--values PATH` | Runtime values file used by the interactive menu |
| `--color auto\|always\|never` | Output color mode; default is `auto` |

With no command, Rigyard opens the one-shot interactive menu. When stdin is not a terminal, it prints help and returns 2.

## Configuration commands

```bash
rigyard validate
rigyard inspect [--format json|yaml]
rigyard resolve [--values FILE] [--set PATH=VALUE] \
  [--non-interactive] [--with-sources] [--format json|yaml]
```

- `validate` checks all configuration and template syntax.
- `inspect` lists inline runtime parameters.
- `resolve` resolves all runtime parameters; `--with-sources` includes value origins.

## Feature commands

```bash
rigyard image build NAME [resolution options]
rigyard container create NAME [--dry-run] [resolution options]
rigyard build NAME [--dry-run] [resolution options]
rigyard test run NAME [--dry-run] [resolution options]
rigyard test report NAME [--dry-run] [resolution options]
rigyard task run NAME [--dry-run] [resolution options]
rigyard scene ACTION SCENE [PROFILE] [scene options] [resolution options]
```

Common resolution options:

| Option | Description |
| --- | --- |
| `--source PATH` | Select a source when duplicate names exist |
| `--values PATH` | Values YAML for this operation |
| `--set PATH=VALUE` | Override one runtime value; repeatable |
| `--non-interactive` | Disable prompts and fail on missing values |

`image build` executes directly and currently has no `--dry-run`. Container creation, project builds, test actions, custom tasks, and scenario start support plan previews. Test and task commands stream user-defined stdout and stderr unchanged; Rigyard does not parse or format their output.

Scenario actions:

| Action | Additional options |
| --- | --- |
| `start` | `--instance NAME`, `--dry-run`, `--no-attach` |
| `stop` | `--instance NAME` |
| `down` | Compose scenarios only; rejects `--instance` |
| `status` | `--instance NAME` |
| `attach` | `--instance NAME`, `--group GROUP` |
| `logs` | `--instance NAME`, `--group GROUP`, `--follow` |

`--instance` is repeatable. Use `rigyard COMMAND --help` for the exact parser surface.

## Workspace initialization

```bash
rigyard init -f PATH [--force] [--alias NAME | --no-alias]
rigyard alias remove [NAME]
```

The command validates the configuration and writes `.rigyard/context.yaml` in the current directory. Resolution order is explicit `--config`, current-directory binding, then current-directory `rigyard.yaml`. Parent directories are not searched.

When the manifest is inside the workspace, the binding records a relative path so the same checkout can use different host and container mount roots. Rebinding the same configuration is idempotent; changing it requires `--force`.

The optional `workspace.command_alias` manifest field creates an executable wrapper in the scripts
directory of the active Conda or virtual environment. `--alias NAME` overrides that value, while
`--no-alias` disables it for one initialization:

```bash
rigyard init -f src/robot/.rigyard/rigyard.yaml
robot build native
```

Rigyard requires the active environment to provide the running Rigyard interpreter, then binds the
wrapper to that interpreter and an absolute configuration path. Deactivating the environment removes
its scripts directory from normal command lookup. Rigyard does not modify `PATH` or write to a
user-wide bin directory. Existing files and symbolic links are protected unless `--force`
explicitly replaces them during initialization.

`rigyard alias remove` uses `workspace.command_alias`; pass `NAME` to remove an alias that was
created with a CLI override. Removal is idempotent and only accepts a regular file carrying Rigyard's
generated marker for the selected configuration. It refuses unrelated files, symbolic links, and
aliases belonging to another project. Project moves require re-running `rigyard init --force`
because environment aliases store an absolute configuration path.

## Interactive menu

The menu offers Build image, Create container, Build project, Test actions for Run and Show results, configuration-enabled custom Tasks, and Scene actions for Start, Stop, and Down. The process exits after one successful, failed, or cancelled action. Menu and direct CLI paths use the same application use cases.

Plan confirmation defaults to `[Y/n]`. Removing and recreating an existing container is the only confirmation that defaults to `[y/N]`.

## Output color

`--color=auto` uses color only when the output stream is a terminal. `NO_COLOR`, `TERM=dumb`, and `--color=never` disable it for CI and redirected logs.
