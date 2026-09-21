# Installation and requirements

## Python

Rigyard requires Python 3.10 or newer.

After the package is published to PyPI, install the CLI in an isolated environment:

```bash
pipx install rigyard
# or
uv tool install rigyard
```

It can also be installed into an active virtual environment:

```bash
python -m pip install rigyard
```

To install the current source tree:

```bash
git clone https://github.com/zz990099/Rigyard.git
cd Rigyard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

Verify the installation:

```bash
rigyard --version
```

Editable installs, tests, and code checks are covered by the [contribution guide](../CONTRIBUTING.md).

## External tools

The Python package does not install these system tools:

| Feature | Host requirement | Container requirement |
| --- | --- | --- |
| Images, containers, and builds | Docker CLI and an accessible Docker daemon | Tools required by project scripts |
| Compose scenarios | Docker Compose v2 (`docker compose`) | Tools required by scenario commands |
| tmux scenarios | tmux and Docker CLI | An interactive shell |

Rigyard currently targets development environments that can run Docker and tmux. Use `docker version`, `docker compose version`, and `tmux -V` to verify the external dependencies.
