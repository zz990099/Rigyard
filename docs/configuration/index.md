# Configuration overview

Rigyard uses schema version 3. The root `rigyard.yaml` is a manifest containing project metadata, workspace and branding defaults, global variables, and paths to domain-specific source files. Images, containers, builds, tests, custom tasks, and scenarios live in separate source files.

```yaml
version: 3

metadata:
  name: robot-development
  description: Robot software development environment

variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}
  CONTAINER_WORKSPACE_ROOT: /workspace

sources:
  images: [config/images.yaml]
  containers: [config/containers.yaml]
  builds: [config/builds.yaml]
  tests: [config/tests.yaml]
  tasks: [config/tasks.yaml]
  scenarios: [config/scenarios.yaml]
```

At least one source kind is required. Each source can be one path or a non-empty list of paths. Paths are relative to the root manifest, not the current directory or the source file.

## File responsibilities

| File | Top-level content | Guide |
| --- | --- | --- |
| `rigyard.yaml` | `version`, `metadata`, `workspace`, `branding`, `variables`, and `sources` | [Root manifest](manifest.md) |
| Image source | Mapping from image names to definitions | [Images](../features/images.md) |
| Container source | Mapping from container names to definitions | [Containers](../features/containers.md) |
| Build source | Mapping from build names to definitions | [Project builds](../features/builds.md) |
| Test source | Mapping from test names to definitions | [Tests](../features/tests.md) |
| Task source | Mapping from task names to definitions | [Custom tasks](../features/tasks.md) |
| Scenario source | Mapping from scenario names to definitions | [Scenarios](../features/scenarios.md) |

A source may use the reserved `description` key as its menu group label:

```yaml
description: Desktop development targets

development:
  image: example/development:latest
  command: [/bin/bash]
```

Different sources may define the same resource name. The menu asks for a source first; direct CLI commands require `--source PATH` to resolve ambiguity. Recursive includes, cross-file inheritance, and merge overlays are not supported.

## Configuration discovery

Rigyard selects the root manifest in this order:

1. Global `--config/-f PATH`.
2. The workspace binding in `.rigyard/context.yaml` in the current directory.
3. `rigyard.yaml` in the current directory.

Workspace bindings apply only to the current directory. Parent directories are not searched. See [Workspace initialization](../reference/cli.md#workspace-initialization).

Use `rigyard context` to print the current directory, the selection source, the workspace marker
when one is active, the resolved root manifest, and every loaded source file. This is useful when
several workspaces share one Python environment.

## Path bases

Unless a feature guide says otherwise, relative host paths are resolved from the directory containing the root manifest:

- Source file paths
- External terminal logo files after template expansion
- Image contexts and Dockerfile fragments
- Container bind-mount sources
- Container lifecycle hook scripts
- Compose files

The `script`, `workdir`, and `setup` fields in builds, tests, tasks, and scenarios are container paths and are not resolved against the host configuration directory.

## Evaluation order

An operation follows these steps:

1. Load and validate the manifest and all source files.
2. Select the resource subtree required by the operation.
3. Resolve [runtime values](runtime-values.md) in that subtree.
4. Expand [global variables and string templates](templates.md).
5. Apply strict type and business-rule validation.
6. Create an immutable plan; `--dry-run` stops here where supported.
7. Invoke Docker or tmux.

Unselected resources do not prompt for runtime values or read host environment variables referenced by templates. `branding.logo_file` is the exception: its templated path is resolved and read when the root configuration is loaded.

## Validation and diagnostics

```bash
rigyard validate
rigyard inspect --format yaml
rigyard resolve --non-interactive --with-sources
```

- `validate` checks every file, field, and template expression without requiring `${env:NAME}` to exist.
- `inspect` lists all inline PromptValues.
- `resolve` resolves runtime values; `--with-sources` includes each value's source.
