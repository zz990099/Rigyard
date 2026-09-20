# Robot development example

This is Rigyard's full reference project. It demonstrates:

- a command alias named `robot` installed in the active Python environment;
- a terminal logo loaded from `branding/logo.txt` through a global variable;
- layered image builds and interactive build arguments;
- development and AArch64 cross-compilation containers;
- `post_create` and `post_start` lifecycle hooks;
- native builds, test execution and user-defined test reports;
- a confirmed menu task and a CLI-only diagnostics task;
- existing-container tmux scenarios and Docker Compose-managed scenarios.

Initialize a disposable workspace from the repository root:

```bash
rigyard init -f examples/robot-development/rigyard.yaml
robot validate
```

Use `rigyard init -f examples/robot-development/rigyard.yaml --no-alias` to bind the workspace
without creating `robot`, or `--alias NAME` to override the configured name. Alias creation requires
the Conda or virtual environment that provides Rigyard to be active. Remove it safely with:

```bash
rigyard alias remove
```

The commands can also be previewed directly:

```bash
rigyard --config examples/robot-development/rigyard.yaml container create development --dry-run
rigyard --config examples/robot-development/rigyard.yaml build native --dry-run
rigyard --config examples/robot-development/rigyard.yaml test run unit --dry-run
rigyard --config examples/robot-development/rigyard.yaml test report unit --dry-run
rigyard --config examples/robot-development/rigyard.yaml task run clean --dry-run
rigyard --config examples/robot-development/rigyard.yaml scene start robot-system development --dry-run
```
