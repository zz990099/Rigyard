# Global variables and string templates

Templates apply to configuration strings and paths. Expansion happens after runtime values are selected, and every string is expanded once.

## Built-in expressions

| Expression | Value |
| --- | --- |
| `${WORKSPACE_ROOT}` | Absolute host path of the active workspace |
| `${RIGYARD_ROOT}` | Absolute host directory containing the root `rigyard.yaml` |
| `${env:NAME}` | Host environment variable; missing variables are errors at resolution time |
| `${date:FORMAT}` | Local time captured at the start of the command |
| `${utcdate:FORMAT}` | The same instant in UTC |
| `${NAME}` | `variables.NAME` from the root manifest |
| `$${...}` | Literal `${...}` without evaluation |

```yaml
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
  CONTAINER_PROJECT_ROOT: /workspace/project

development:
  image: robot/app:${date:%Y%m%d}
  name: dev_${env:USER}_${date:%Y%m%d%H%M}
  mounts:
    - ${PROJECT_ROOT}:${CONTAINER_PROJECT_ROOT}
```

## Root path semantics

`WORKSPACE_ROOT` and `RIGYARD_ROOT` are host values known to Rigyard:

- With `rigyard init`, `WORKSPACE_ROOT` is the directory that was initialized.
- With direct `--config` use or a local `rigyard.yaml`, `WORKSPACE_ROOT` is the current directory.
- `RIGYARD_ROOT` is always the parent directory of the actual root manifest.

Rigyard does not define or infer `PROJECT_ROOT`; project layout is user-owned semantics:

```yaml
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
```

Because Rigyard cannot infer Docker mount destinations, container-side paths must also be explicit:

```yaml
variables:
  CONTAINER_WORKSPACE_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: /workspace/src/robot
```

## User variables

Variables are evaluated in declaration order and may reference built-in roots, the host environment, date expressions, and earlier variables:

```yaml
variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}/..
  CONFIG_ROOT: ${PROJECT_ROOT}/config
```

Forward references and cycles fail. A user variable with the same name overrides `WORKSPACE_ROOT` or `RIGYARD_ROOT`; avoid overriding those names unless a project intentionally changes their semantics.

## Date formats

Date expressions support a restricted set of `strftime` directives, including:

| Directive | Meaning |
| --- | --- |
| `%Y` | Four-digit year |
| `%m` | Two-digit month |
| `%d` | Two-digit day |
| `%H` | Hour |
| `%M` | Minute |
| `%S` | Second |
| `%z` | UTC offset |
| `%%` | Literal `%` |

A command captures time once, so timestamps remain consistent across all fields in that operation.

## Expansion scope

Templates recursively process selected operation values in strings, paths, lists, tuples, mapping values, resolved PromptValues, and static prompt options.

`branding.logo_file` is resolved eagerly because Rigyard must load the terminal asset with the root
configuration. It supports the same expressions, including variables declared earlier in
`variables`. If its path uses `${env:NAME}`, that environment variable must exist even during
`rigyard validate`.

Templates do not process mapping keys, resource names, prompt messages, dynamic source settings, or expressions produced by an earlier replacement. For example, if `VALUE='${date:%Y}'`, `${env:VALUE}` remains the literal string `${date:%Y}`.

## Two forms of environment lookup

General string template:

```yaml
name: dev_${env:USER}
```

Container and hook environment fields also accept a structured host reference:

```yaml
environment:
  DISPLAY: {env: DISPLAY}
  OPTIONAL_TOKEN: {env: TOKEN, default: ""}
```

`${env:NAME}` works in any supported string and may appear in plans or error output. `{env: NAME, default: ...}` is limited to supported container environment fields and participates in sensitive-value redaction. Do not use general templates for secrets that require automatic redaction.

## Validation rules

- Environment variable names must match `[A-Za-z_][A-Za-z0-9_]*`.
- Nested expressions such as `${env:${NAME}}` are not supported.
- Unknown template kinds are rejected.
- Expressions must be closed, and results cannot contain NUL bytes.
- Except for the eagerly loaded `branding.logo_file`, `rigyard validate` checks syntax without reading `${env:NAME}`.
- A missing environment value fails only when the selected configuration is resolved.
