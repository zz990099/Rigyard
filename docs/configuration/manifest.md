# Root manifest

The root manifest currently requires schema version 3 and rejects unknown fields.

```yaml
version: 3
metadata:
  name: robot-development
  description: Optional description
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
sources:
  images: config/images.yaml
  containers: [config/containers.yaml]
  builds: config/builds.yaml
  scenarios: config/scenarios.yaml
```

## Fields

| Field | Type | Required | Rule |
| --- | --- | ---: | --- |
| `version` | integer | yes | Must be `3` |
| `metadata` | mapping | yes | Project display metadata |
| `metadata.name` | string | yes | Must not be blank |
| `metadata.description` | string | no | Project description |
| `variables` | string mapping | no | Defaults to empty; see [Templates](templates.md) |
| `sources` | mapping | yes | Must contain at least one source kind |
| `sources.images` | path or path list | no | Image sources |
| `sources.containers` | path or path list | no | Container sources |
| `sources.builds` | path or path list | no | Build sources |
| `sources.scenarios` | path or path list | no | Scenario sources |

Source lists cannot be empty. All source paths are relative to the root manifest. Configuration files must be UTF-8 YAML.

## Definition names

Image, container, build, scenario, layer, profile, and group names match:

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
