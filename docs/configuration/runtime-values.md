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
base: [always-retained]     # Input with merge: append only
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
  merge: replace | append   # Input only; defaults to replace
  input_template: ${INPUT}  # Input only; exactly one placeholder
```

`default` is optional. Without it, non-interactive execution requires a values file, an environment variable, or `--set`. Existing configurations keep replacement behavior because `merge` defaults to `replace`.

## Modes

| Mode | Result | Rules |
| --- | --- | --- |
| `input` | Input string, later converted by the business field if needed | `repeat: true` returns a list |
| `confirm` | Boolean | The default must be a boolean |
| `select` | Selected candidate | Requires non-empty `options` or a `source` |

The final business field validates the resolved type and range.

## Input composition

An input prompt can transform its selected value before the business field receives it. `${INPUT}` is a prompt-local placeholder and must appear exactly once in `input_template`:

```yaml
name:
  default: robot-cross
  prompt:
    mode: input
    message: Enter the container prefix
    input_template: "${INPUT}_dev"
```

The default resolves to `robot-cross_dev`; entering `trial` resolves to `trial_dev`. Values files, environment overrides, and `--set` supply the same raw input and receive the same transformation.

List fields can either replace the whole value or append transformed entries to a fixed base. Append mode requires an explicit list-valued `base`:

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

This always retains the workspace mount and adds one user-selected sysroot mount. Add `repeat: true` and use a list-valued default when multiple additions are allowed. With the default `merge: replace`, the selected value replaces the complete business field and `base` is not allowed.

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

Built-in dynamic providers query host Docker only when the prompt is displayed. Use
`docker-containers` to select an existing container:

```yaml
container:
  default: robot_development
  prompt:
    mode: select
    message: Select a build container
    source:
      provider: docker-containers
      filter: "^robot_"
      running_only: false
```

- `filter` is an optional regular expression matched against container names.
- `running_only` is specific to `docker-containers` and defaults to `false`.
- `running_only` only filters prompt candidates. Build, test, and task lifecycle behavior is
  controlled independently by each definition's `start_container` field.

Use `docker-images` to select a tagged local image. The filter is matched against the full
`repository:tag` reference:

```yaml
image:
  default: example/robot-development:latest
  prompt:
    mode: select
    message: Select the development image
    source:
      provider: docker-images
      filter: "^example/robot-development:"
```

Image candidates show the short image ID, creation age, and size. Untagged dangling images are
omitted because they do not have a stable repository/tag reference.

Both providers share these resolution rules:

- Dynamic options are an open set; explicit values need not appear in the query result.
- If Docker is unavailable or no candidates exist, interactive mode falls back to ordinary input.
- Non-interactive execution and explicit values do not query the provider.

## Value sources and precedence

From lowest to highest precedence:

1. Inline `default`
2. Values YAML
3. `RIGYARD_PARAM_*` environment variable
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
rigyard --values local-values.yaml
rigyard image build development --values local-values.yaml
```

A values file supplies user input; it is not a project source and does not merge definitions.

### Environment variables

The full path is uppercased and every non-alphanumeric character becomes an underscore:

```text
containers.development.privileged
→ RIGYARD_PARAM_CONTAINERS_DEVELOPMENT_PRIVILEGED
```

Rigyard rejects configurations in which two parameter paths map to the same environment variable name.

### CLI overrides

`--set` is repeatable, and values use YAML scalar, list, or mapping syntax:

```bash
rigyard container create development \
  --non-interactive \
  --set containers.development.privileged=true \
  --set 'containers.development.mounts=["./:/workspace"]'
```

Unknown paths are errors, preventing silent spelling mistakes.

## Resolution ordering

A PromptValue first selects its raw value. Rigyard then applies `input_template`, performs the configured append or replacement, expands [global string templates](templates.md) recursively, and finally validates the business field. Defaults, bases, and explicit values may therefore contain global templates:

```yaml
name:
  default: dev_${env:USER}
  prompt:
    mode: input
    message: Container name
```

The prompt displays the rendered default. Pressing Enter still selects the raw default, which is expanded during the common template phase.

`${INPUT}` is recognized only in `prompt.input_template`; it is not a global variable. Any global expressions in `input_template`, such as `${CONTAINER_WORKSPACE_ROOT}`, are expanded after the input substitution.
