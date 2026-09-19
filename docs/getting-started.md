# Getting started

This tutorial uses the repository examples to demonstrate configuration loading and plan previews without requiring an image build.

## 1. Install Rigyard

Follow the [installation guide](installation.md), then verify the command:

```bash
rigyard --version
```

## 2. Validate the example project

From the repository root, run:

```bash
rigyard --config examples/rigyard.yaml validate
```

The root manifest references separate image, container, build, test, task, and scenario sources. `validate` reads every source and checks YAML, field types, and template syntax without invoking Docker.

## 3. Inspect runtime values

```bash
rigyard --config examples/rigyard.yaml inspect
```

The output lists interactive parameters and their `RIGYARD_PARAM_*` environment variable names. Resolve all values non-interactively with:

```bash
rigyard --config examples/rigyard.yaml resolve \
  --non-interactive \
  --set images.development.base=ubuntu:24.04
```

## 4. Preview plans

These commands complete selection, runtime value resolution, and planning without invoking Docker:

```bash
rigyard --config examples/rigyard.yaml container create development --dry-run
rigyard --config examples/rigyard.yaml build native --dry-run
rigyard --config examples/rigyard.yaml test run unit --dry-run
rigyard --config examples/rigyard.yaml test report unit --dry-run
rigyard --config examples/rigyard.yaml task run clean --dry-run
rigyard --config examples/rigyard.yaml scene start robot-system development --dry-run
```

`image build` currently has no dry-run mode. Use `validate` and `resolve` to check its configuration and values before building.

## 5. Bind a workspace

When the everyday working directory differs from the configuration directory, run this command from the working directory:

```bash
rigyard init -f path/to/rigyard.yaml
rigyard validate
```

The binding applies only to that directory; Rigyard does not search parent directories. Initialization can also create a project-local command:

```bash
rigyard init -f path/to/rigyard.yaml --alias xxxbot
./xxxbot validate
```

Continue with the [configuration overview](configuration/index.md) or select a [core feature](index.md#core-features).
