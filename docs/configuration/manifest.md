# Root manifest

The root manifest currently requires schema version 3 and rejects unknown fields.

```yaml
version: 3
metadata:
  name: robot-development
  description: Optional description
branding:
  logo: |
     ____  _                       _
    |  _ \(_) __ _ _   _  __ _ _ __ __| |
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
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
| `branding` | mapping | no | Interactive terminal branding |
| `branding.logo` | string | no | UTF-8 multiline terminal logo |
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

When `branding.logo` is omitted, the interactive menu displays Rigyard's built-in logo. Override it with a YAML block scalar:

```yaml
branding:
  logo: |
     _   _  __  __  ____
    | | | ||  \/  ||  _ \
    | |_| || |\/| || |_) |
    |  _  || |  | ||  __/
    |_| |_||_|  |_||_|
```

The logo is literal display text: template expressions are not expanded. Rigyard removes trailing line breaks and applies the menu's `title` style, so custom ANSI escape sequences are neither necessary nor accepted. The `--color` option and `NO_COLOR` continue to control colour for the whole menu.

For predictable output across terminals, prefer printable ASCII. UTF-8 text is supported, with full-width characters counted as two display columns. A logo may contain at most 12 lines, each at most 100 display columns, and at most 8 KiB of UTF-8 data. Control characters, including tabs and terminal escape sequences, are rejected.

The logo is shown only by the interactive menu. Commands, help output, redirected output, and other non-TTY use remain machine-friendly.

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
