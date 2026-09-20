# Getting started

This tutorial uses the full robot-development example to demonstrate configuration loading and plan previews without requiring an image build. For the smallest runnable introduction, see [`examples/minimal`](../examples/minimal/README.md).

## 1. Install Rigyard

Follow the [installation guide](installation.md), then verify the command:

```bash
rigyard --version
```

## 2. Validate the example project

From the repository root, run:

```bash
rigyard --config examples/robot-development/rigyard.yaml validate
```

The root manifest references separate image, container, build, test, task, and scenario sources. `validate` reads every source and checks YAML, field types, and template syntax without invoking Docker.

## 3. Inspect runtime values

```bash
rigyard --config examples/robot-development/rigyard.yaml inspect
```

The output lists interactive parameters and their `RIGYARD_PARAM_*` environment variable names. Resolve all values non-interactively with:

```bash
rigyard --config examples/robot-development/rigyard.yaml resolve \
  --non-interactive \
  --set images.development.base=ubuntu:24.04
```

## 4. Preview plans

These commands complete selection, runtime value resolution, and planning without invoking Docker:

```bash
rigyard --config examples/robot-development/rigyard.yaml container create development --dry-run
rigyard --config examples/robot-development/rigyard.yaml build native --dry-run
rigyard --config examples/robot-development/rigyard.yaml test run unit --dry-run
rigyard --config examples/robot-development/rigyard.yaml test report unit --dry-run
rigyard --config examples/robot-development/rigyard.yaml task run clean --dry-run
rigyard --config examples/robot-development/rigyard.yaml scene start robot-system development --dry-run
```

`image build` currently has no dry-run mode. Use `validate` and `resolve` to check its configuration and values before building.

## 5. Bind a workspace

When the everyday working directory differs from the configuration directory, run this command from the working directory:

```bash
rigyard init -f examples/robot-development/rigyard.yaml
robot validate
```

The binding applies only to that directory; Rigyard does not search parent directories. This
example configures `workspace.command_alias: robot`. With the Python environment that provides
Rigyard active, initialization installs `robot` into that environment's scripts directory. A CLI
option can override or disable it:

```bash
rigyard init -f examples/robot-development/rigyard.yaml --alias xxxbot
xxxbot validate
rigyard init -f examples/robot-development/rigyard.yaml --no-alias --force
```

Remove the configured Alias from the active environment when it is no longer needed:

```bash
rigyard alias remove
```

Continue with the [configuration overview](configuration/index.md) or select a [core feature](index.md#core-features).
