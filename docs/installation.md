# Installation and requirements

## Quick setup (Linux)

The setup script requires Bash, a network connection, and either `curl` or `wget`. It does not
require an existing Python installation or Conda. From a checkout of this repository:

```bash
git clone https://github.com/zz990099/Rigyard.git
cd Rigyard
bash scripts/bootstrap.sh
source scripts/activate.sh
rigyard --version
```

The script shows the Rigyard logo, checks Docker, Docker Compose v2, and tmux, then finds or installs
uv. It uses uv-managed Python 3.12 to create an isolated venv in
`${XDG_DATA_HOME:-$HOME/.local/share}/rigyard/venv` and installs Rigyard from the current checkout.
It installs a missing uv executable in the adjacent `rigyard/bin` directory without changing shell
startup files. Re-running the script reuses the venv and reinstalls Rigyard from the checkout.
Docker and tmux checks are advisory: missing tools are reported but do not block the Python setup.
The script does not install or configure system packages and does not need `sudo`.

In every new Bash session, activate the environment with:

```bash
source /path/to/Rigyard/scripts/activate.sh
```

Activation requires a completed setup. It exits without changing your shell if another venv or
Conda environment is already active; deactivate that environment first. `source` is required:
running `bash scripts/activate.sh` cannot change the calling terminal. Once active, `rigyard init`
can install workspace command aliases into this shared venv. Rigyard selects the nearest workspace
at command execution time, so one venv can serve multiple workspaces.

## Manual installation

The package requires Python 3.10 or newer. If you prefer Conda, create and activate your own
environment and install from the checkout:

```bash
conda create -n rigyard python=3.12
conda activate rigyard
python -m pip install .
```

Alternatively, install into any existing compatible venv. The Bash setup script always targets its
dedicated uv environment and does not modify an active Conda environment. Editable installs, tests,
and code checks are covered by the [contribution guide](../CONTRIBUTING.md).

## External tools

The Python package does not install these system tools:

| Feature | Host requirement | Container requirement |
| --- | --- | --- |
| Images, containers, and builds | Docker CLI and an accessible Docker daemon | Tools required by project scripts |
| Compose scenarios | Docker Compose v2 (`docker compose`) | Tools required by scenario commands |
| tmux scenarios | tmux and Docker CLI | An interactive shell |

The setup script checks `docker info`, `docker compose version`, and whether tmux is available.
When Docker is unavailable, follow the official Docker installation instructions for your Linux
distribution; check the selected Docker context and current user's daemon access if the CLI is
present but the daemon cannot be reached. Install tmux using your distribution's package manager
if you use scenarios. Rigyard validates the dependencies needed by each operation at runtime.
