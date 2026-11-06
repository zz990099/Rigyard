# Installation and requirements

Rigyard requires Python 3.10 or newer.

## From PyPI

```bash
python -m pip install rigyard
```

To select a release, use `python -m pip install rigyard==VERSION`.

## From source

```bash
git clone https://github.com/zz990099/Rigyard.git
cd Rigyard
python -m pip install .
```

For editable installation and development checks, see the [contribution guide](../CONTRIBUTING.md).

Verify the installation with `rigyard --version`, then follow [Getting started](getting-started.md).
The command directory must be on `PATH` for `rigyard` and generated command aliases to be found.

## External tools

Install these tools separately for the features you use:

| Feature | Host requirement | Container requirement |
| --- | --- | --- |
| Images, containers, builds, tests, and tasks | Docker CLI and an accessible Docker daemon | Tools required by project scripts |
| Compose scenarios | Docker Compose v2 (`docker compose`) | Tools required by scenario commands |
| tmux scenarios | tmux and Docker CLI | An interactive shell |
| Scene autostart | Linux with systemd and local Docker | Tools required by scenario commands |

Rigyard validates the dependencies needed by each operation at runtime. Configuration validation
and supported `--dry-run` plan previews do not require Docker or tmux.
