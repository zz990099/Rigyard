# Runtime values

Any Runtime-typed business field can contain a fixed value or an inline `default + prompt` object. No separate top-level parameter declaration is required.

```yaml
privileged:
  default: false
  prompt:
    mode: confirm
    message: Enable privileged mode?
```

Only the selected resource is resolved. Building `images.development`, for example, does not prompt for values belonging to other images or containers.

## PromptValue structure

```yaml
default: optional-value
prompt:
  mode: input | confirm | select
  message: Message shown to the user
  options: [one, two]       # Static select only
  source:                   # Dynamic select; mutually exclusive with options
    provider: docker-containers
    filter: "^robot_"
    running_only: true
  repeat: false             # Input only
  item_hint: VALUE          # Hint for repeated input
```

`default` is optional. Without it, non-interactive execution requires a values file, an environment variable, or `--set`.

## Modes

| Mode | Result | Rules |
| --- | --- | --- |
| `input` | Input string, later converted by the business field if needed | `repeat: true` returns a list |
| `confirm` | Boolean | The default must be a boolean |
| `select` | Selected candidate | Requires non-empty `options` or a `source` |

The final business field validates the resolved type and range.

## Static options

```yaml
base:
  default: ubuntu:22.04
  prompt:
    mode: select
    message: Select the base image
    options: [ubuntu:22.04, ubuntu:24.04]
```

Interactive and explicit values must match static options. The default must also be one of the options.

## Dynamic options

The built-in `docker-containers` provider queries host Docker only when the prompt is displayed:

```yaml
container:
  default: robot_development
  prompt:
    mode: select
    message: Select a build container
    source:
      provider: docker-containers
      filter: "^robot_"
      running_only: true
```

- `filter` is an optional regular expression matched against container names.
- `running_only` defaults to `false`.
- Dynamic options are an open set; explicit values need not appear in the query result.
- If Docker is unavailable or no candidates exist, interactive mode falls back to ordinary input.
- Non-interactive execution and explicit values do not query the provider.

## Value sources and precedence

From lowest to highest precedence:

1. Inline `default`
2. Values YAML
3. `TOOL_PARAM_*` environment variable
4. `--set PATH=VALUE`
5. Interactive input when no explicit source exists

Interactive mode shows a prompt even when a default exists; pressing Enter accepts it. `--non-interactive` never prompts and fails when a required value is missing.

### Values files

The values structure mirrors full configuration paths:

```yaml
images:
  development:
    base: ubuntu:24.04
containers:
  development:
    privileged: true
scenarios:
  robot-system:
    profiles:
      development:
        attach: false
```

```bash
toolchain --values local-values.yaml
toolchain image build development --values local-values.yaml
```

A values file supplies user input; it is not a project source and does not merge definitions.

### Environment variables

The full path is uppercased and every non-alphanumeric character becomes an underscore:

```text
containers.development.privileged
→ TOOL_PARAM_CONTAINERS_DEVELOPMENT_PRIVILEGED
```

Toolchain rejects configurations in which two parameter paths map to the same environment variable name.

### CLI overrides

`--set` is repeatable, and values use YAML scalar, list, or mapping syntax:

```bash
toolchain container create development \
  --non-interactive \
  --set containers.development.privileged=true \
  --set 'containers.development.mounts=["./:/workspace"]'
```

Unknown paths are errors, preventing silent spelling mistakes.

## Template ordering

A PromptValue first selects its raw value. [String templates](templates.md) then expand recursively, followed by business-field validation. Defaults and explicit values may therefore contain templates:

```yaml
name:
  default: dev_${env:USER}
  prompt:
    mode: input
    message: Container name
```

The prompt displays the rendered default. Pressing Enter still selects the raw default, which is expanded during the common template phase.
