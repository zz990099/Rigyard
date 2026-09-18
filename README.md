# Toolchain

Toolchain is a configuration-driven CLI for containerized robotics development. A single project manifest organizes layered image builds, development containers, project builds inside containers, and multi-process debugging scenarios managed by tmux.

## Features

- Build layered images from ordered Dockerfile fragments.
- Create reproducible development containers and run lifecycle hooks.
- Run project build scripts inside existing containers.
- Start tmux debugging scenarios in existing containers or Docker Compose services.
- Reuse configuration with global variables, string templates, and interactive runtime values.
- Use the same application behavior through direct commands or a one-shot interactive menu.

## Requirements

- Python 3.10 or newer
- Docker; Compose scenarios require Docker Compose v2
- Scenario support requires tmux on the host and an interactive shell in each target container

## Installation

After the project is published to PyPI, install it as an isolated command-line tool:

```bash
pipx install robot-toolchain
# or
uv tool install robot-toolchain
```

To install the current source tree:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

See the [contribution guide](https://github.com/zz990099/toolchain/blob/main/CONTRIBUTING.md) for development installation and checks.

## Quick start

By default, Toolchain reads `toolchain.yaml` from the current directory:

```yaml
version: 3

metadata:
  name: robot-development

variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}
  CONTAINER_WORKSPACE_ROOT: /workspace

sources:
  images: [config/images.yaml]
  containers: [config/containers.yaml]
  builds: [config/builds.yaml]
  scenarios: [config/scenarios.yaml]
```

Validate the configuration and run configured operations:

```bash
toolchain validate
toolchain image build development
toolchain container create development
toolchain build native
toolchain scene start robot-system development
```

Run `toolchain` without a subcommand to open the one-shot interactive menu:

```bash
toolchain
```

When the manifest lives elsewhere, pass it explicitly or bind the current workspace:

```bash
toolchain --config path/to/toolchain.yaml validate
toolchain init -f path/to/toolchain.yaml --alias xxxbot
./xxxbot build native
```

## Documentation

- [Getting started](https://github.com/zz990099/toolchain/blob/main/docs/getting-started.md)
- [Installation and requirements](https://github.com/zz990099/toolchain/blob/main/docs/installation.md)
- [Configuration overview](https://github.com/zz990099/toolchain/blob/main/docs/configuration/index.md)
- [Global variables and string templates](https://github.com/zz990099/toolchain/blob/main/docs/configuration/templates.md)
- [Runtime values](https://github.com/zz990099/toolchain/blob/main/docs/configuration/runtime-values.md)
- [Images](https://github.com/zz990099/toolchain/blob/main/docs/features/images.md)
- [Containers](https://github.com/zz990099/toolchain/blob/main/docs/features/containers.md)
- [Project builds](https://github.com/zz990099/toolchain/blob/main/docs/features/builds.md)
- [Scenarios](https://github.com/zz990099/toolchain/blob/main/docs/features/scenarios.md)
- [CLI reference](https://github.com/zz990099/toolchain/blob/main/docs/reference/cli.md)
- [Configuration schema reference](https://github.com/zz990099/toolchain/blob/main/docs/reference/configuration-schema.md)
- [Exit codes](https://github.com/zz990099/toolchain/blob/main/docs/reference/exit-codes.md)

Complete examples are available in [`examples/`](https://github.com/zz990099/toolchain/tree/main/examples).

## License

[MIT](https://github.com/zz990099/toolchain/blob/main/LICENSE)
