# Rigyard

Rigyard is a configuration-driven CLI for containerized robotics development. A single project manifest organizes layered image builds, development containers, project builds and tests inside containers, project-specific tasks, and multi-process debugging scenarios managed by tmux.

## Features

- Build layered images from ordered Dockerfile fragments.
- Create reproducible development containers and run lifecycle hooks.
- Run project build scripts inside existing containers.
- Run user-defined test and test-result commands inside existing containers.
- Expose constrained project-specific container tasks through the CLI and interactive menu.
- Start tmux debugging scenarios in existing containers or Docker Compose services.
- Reuse configuration with global variables, string templates, and interactive runtime values.
- Use the same application behavior through direct commands or a branded one-shot interactive menu.

## Requirements

- Python 3.10 or newer
- Docker; Compose scenarios require Docker Compose v2
- Scenario support requires tmux on the host and an interactive shell in each target container

## Installation

After the project is published to PyPI, install it as an isolated command-line tool:

```bash
pipx install rigyard
# or
uv tool install rigyard
```

To install the current source tree:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

See the [contribution guide](https://github.com/zz990099/Rigyard/blob/main/CONTRIBUTING.md) for development installation and checks.

## Quick start

By default, Rigyard reads `rigyard.yaml` from the current directory:

```yaml
version: 3

metadata:
  name: robot-development

workspace:
  command_alias: robot

variables:
  PROJECT_ROOT: ${RIGYARD_ROOT}
  BRANDING_ROOT: ${PROJECT_ROOT}/branding
  CONTAINER_WORKSPACE_ROOT: /workspace

branding:
  logo_file: ${BRANDING_ROOT}/logo.txt

sources:
  images: [config/images.yaml]
  containers: [config/containers.yaml]
  builds: [config/builds.yaml]
  tests: [config/tests.yaml]
  tasks: [config/tasks.yaml]
  scenarios: [config/scenarios.yaml]
```

Validate the configuration and run configured operations:

```bash
rigyard validate
rigyard image build development
rigyard container create development
rigyard build native
rigyard test run unit
rigyard test report unit
rigyard task run clean
rigyard scene start robot-system development
```

Run `rigyard` without a subcommand to open the one-shot interactive menu:

```bash
rigyard
```

With the built-in logo and the example sources configured, the menu looks like this (colours omitted):

```text
$ rigyard
██████╗ ██╗ ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗
██╔══██╗██║██╔════╝ ╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗
██████╔╝██║██║  ███╗ ╚████╔╝ ███████║██████╔╝██║  ██║
██╔══██╗██║██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██║  ██║
██║  ██║██║╚██████╔╝   ██║   ██║  ██║██║  ██║██████╔╝
╚═╝  ╚═╝╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝

Project: robot-development
Configuration: /workspace/robot-development/rigyard.yaml

1) Build image
2) Create container
3) Build project
4) Scene…
5) Test…
6) Tasks…
0) Exit
Select [0-6]:
```

Custom terminal logos can be inline or loaded from a templated path; see the [root manifest guide](https://github.com/zz990099/Rigyard/blob/main/docs/configuration/manifest.md#terminal-logo).

When the manifest lives elsewhere, pass it explicitly or bind the current workspace:

```bash
rigyard --config path/to/rigyard.yaml validate
rigyard init -f path/to/rigyard.yaml
./robot build native
```

## Documentation

- [Getting started](https://github.com/zz990099/Rigyard/blob/main/docs/getting-started.md)
- [Installation and requirements](https://github.com/zz990099/Rigyard/blob/main/docs/installation.md)
- [Configuration overview](https://github.com/zz990099/Rigyard/blob/main/docs/configuration/index.md)
- [Global variables and string templates](https://github.com/zz990099/Rigyard/blob/main/docs/configuration/templates.md)
- [Runtime values](https://github.com/zz990099/Rigyard/blob/main/docs/configuration/runtime-values.md)
- [Images](https://github.com/zz990099/Rigyard/blob/main/docs/features/images.md)
- [Containers](https://github.com/zz990099/Rigyard/blob/main/docs/features/containers.md)
- [Project builds](https://github.com/zz990099/Rigyard/blob/main/docs/features/builds.md)
- [Tests](https://github.com/zz990099/Rigyard/blob/main/docs/features/tests.md)
- [Custom tasks](https://github.com/zz990099/Rigyard/blob/main/docs/features/tasks.md)
- [Scenarios](https://github.com/zz990099/Rigyard/blob/main/docs/features/scenarios.md)
- [CLI reference](https://github.com/zz990099/Rigyard/blob/main/docs/reference/cli.md)
- [Configuration schema reference](https://github.com/zz990099/Rigyard/blob/main/docs/reference/configuration-schema.md)
- [Exit codes](https://github.com/zz990099/Rigyard/blob/main/docs/reference/exit-codes.md)

Start with the [`minimal`](https://github.com/zz990099/Rigyard/tree/main/examples/minimal) example or browse the complete [`robot-development`](https://github.com/zz990099/Rigyard/tree/main/examples/robot-development) reference project.

## License

[MIT](https://github.com/zz990099/Rigyard/blob/main/LICENSE)

---

Powered by **Codex** — AI-assisted development and documentation.
