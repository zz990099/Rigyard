# Root manifest

The root manifest currently requires schema version 3 and rejects unknown fields.

```yaml
version: 3
metadata:
  name: robot-development
  description: Optional description
workspace:
  command_alias: robot
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
  BRANDING_ROOT: ${PROJECT_ROOT}/branding
branding:
  logo_file: ${BRANDING_ROOT}/logo.txt
sources:
  images: config/images.yaml
  containers: [config/containers.yaml]
  builds: config/builds.yaml
  tests: config/tests.yaml
  tasks: config/tasks.yaml
  scenarios: config/scenarios.yaml
```

## Fields

| Field | Type | Required | Rule |
| --- | --- | ---: | --- |
| `version` | integer | yes | Must be `3` |
| `metadata` | mapping | yes | Project display metadata |
| `metadata.name` | string | yes | Must not be blank |
| `metadata.description` | string | no | Project description |
| `workspace` | mapping | no | Defaults used by workspace initialization |
| `workspace.command_alias` | string | no | Project-local command created by `rigyard init` |
| `branding` | mapping | no | Interactive terminal branding |
| `branding.logo` | string | no | UTF-8 multiline terminal logo |
| `branding.logo_file` | path | no | UTF-8 text file containing the terminal logo |
| `variables` | string mapping | no | Defaults to empty; see [Templates](templates.md) |
| `sources` | mapping | yes | Must contain at least one source kind |
| `sources.images` | path or path list | no | Image sources |
| `sources.containers` | path or path list | no | Container sources |
| `sources.builds` | path or path list | no | Build sources |
| `sources.tests` | path or path list | no | Test sources |
| `sources.tasks` | path or path list | no | Custom task sources |
| `sources.scenarios` | path or path list | no | Scenario sources |

Source lists cannot be empty. All source paths are relative to the root manifest. Configuration files must be UTF-8 YAML.

## Terminal logo

When both branding fields are omitted, the interactive menu displays Rigyard's built-in logo.
Override it with a YAML block scalar:

```yaml
branding:
  logo: |
     _   _  __  __  ____
    | | | ||  \/  ||  _ \
    | |_| || |\/| || |_) |
    |  _  || |  | ||  __/
    |_| |_||_|  |_||_|
```

For a separate asset, use `logo_file`. Its path supports the normal string templates, including
root paths and variables declared earlier in `variables`:

```yaml
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
  BRANDING_ROOT: ${PROJECT_ROOT}/branding
branding:
  logo_file: ${BRANDING_ROOT}/logo.txt
```

After expansion, absolute paths are used directly and `~` is expanded. A remaining relative path
is resolved from the root manifest directory. This lets a variable point to any user-selected
location without making plain relative paths depend on the current directory. `branding.logo` and
`branding.logo_file` are mutually exclusive. The external file is read while the configuration is
loaded, so any environment variable used to locate it must be available at that time.

Logo content is always literal display text: template expressions inside either the inline value or
the external file are not expanded. Rigyard removes trailing line breaks and applies the menu's
`title` style, so custom ANSI escape sequences are neither necessary nor accepted. The `--color`
option and `NO_COLOR` continue to control colour for the whole menu.

For predictable output across terminals, prefer printable ASCII. UTF-8 text is supported, with full-width characters counted as two display columns. A logo may contain at most 12 lines, each at most 100 display columns, and at most 8 KiB of UTF-8 data. Control characters, including tabs and terminal escape sequences, are rejected.

The logo is shown only by the interactive menu. Commands, help output, redirected output, and other non-TTY use remain machine-friendly.

## Workspace defaults

`workspace.command_alias` defines the project-local executable created by `rigyard init`:

```yaml
workspace:
  command_alias: robot
```

Names must begin with a letter, may contain letters, digits, `_` and `-`, and cannot be `rigyard`.
Use `rigyard init --alias NAME` to override the configured name or `rigyard init --no-alias` to
initialize without creating it. See [Workspace initialization](../reference/cli.md#workspace-initialization).

## Definition names

Image, container, build, test, task, scenario, layer, profile, and group names match:

```text
[A-Za-z][A-Za-z0-9_.-]*
```

Scenario instances become tmux window names during planning and must match:

```text
[A-Za-z0-9][A-Za-z0-9_-]*
```

## Global variables

Variable names match `[A-Za-z_][A-Za-z0-9_]*`, and values must be strings. Variables are evaluated in YAML declaration order:

```yaml
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
  CONFIG_ROOT: ${PROJECT_ROOT}/config
  CONTAINER_PROJECT_ROOT: /workspace/project
```

They may reference built-in roots, host environment variables, dates, and previously declared variables. Forward references are invalid. See [Global variables and string templates](templates.md).
