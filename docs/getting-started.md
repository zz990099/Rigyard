# Getting started

This tutorial uses the repository examples to demonstrate configuration loading and plan previews without requiring an image build.

## 1. Install Toolchain

Follow the [installation guide](installation.md), then verify the command:

```bash
toolchain --version
```

## 2. Validate the example project

From the repository root, run:

```bash
toolchain --config examples/toolchain.yaml validate
```

The root manifest references separate image, container, build, and scenario sources. `validate` reads every source and checks YAML, field types, and template syntax without invoking Docker.

## 3. Inspect runtime values

```bash
toolchain --config examples/toolchain.yaml inspect
```

The output lists interactive parameters and their `TOOL_PARAM_*` environment variable names. Resolve all values non-interactively with:

```bash
toolchain --config examples/toolchain.yaml resolve \
  --non-interactive \
  --set images.development.base=ubuntu:24.04
```

## 4. Preview plans

These commands complete selection, runtime value resolution, and planning without invoking Docker:

```bash
toolchain --config examples/toolchain.yaml container create development --dry-run
toolchain --config examples/toolchain.yaml build native --dry-run
toolchain --config examples/toolchain.yaml scene start robot-system development --dry-run
```

`image build` currently has no dry-run mode. Use `validate` and `resolve` to check its configuration and values before building.

## 5. Bind a workspace

When the everyday working directory differs from the configuration directory, run this command from the working directory:

```bash
toolchain init -f path/to/toolchain.yaml
toolchain validate
```

The binding applies only to that directory; Toolchain does not search parent directories. Initialization can also create a project-local command:

```bash
toolchain init -f path/to/toolchain.yaml --alias xxxbot
./xxxbot validate
```

Continue with the [configuration overview](configuration/index.md) or select a [core feature](index.md#core-features).
