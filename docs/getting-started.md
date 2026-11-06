# Getting started

This tutorial uses the small [robot-development example](../examples/robot-development/README.md)
to demonstrate configuration loading and plan previews without requiring an image build.
For a container and task introduction, see [`examples/minimal`](../examples/minimal/README.md).

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

The root manifest references `images/image.yaml`, `containers/containers.yaml`,
`builds/build.yaml`, and `scenarios/nav2-tb3.yaml`. `validate` reads every source and
checks YAML, field types, and template syntax without invoking Docker.

## 3. Inspect runtime values

```bash
rigyard --config examples/robot-development/rigyard.yaml inspect
```

The output lists interactive parameters and their `RIGYARD_PARAM_*` environment variable names. Resolve all values non-interactively with:

```bash
rigyard --config examples/robot-development/rigyard.yaml resolve \
  --non-interactive \
  --set containers.development.name=robot_dev_example
```

## 4. Preview plans

These commands complete selection, runtime value resolution, and planning without invoking Docker:

```bash
rigyard --config examples/robot-development/rigyard.yaml container create development --dry-run --non-interactive
rigyard --config examples/robot-development/rigyard.yaml build development --dry-run --non-interactive
rigyard --config examples/robot-development/rigyard.yaml scene start nav2-tb3 --dry-run --non-interactive
```

`image build` currently has no dry-run mode. Use `validate` and `resolve` to check its configuration and values before building.

Non-interactive previews use the default image and container names without querying
Docker. Real interactive operations offer local images and containers. To run the
simulation later, follow the example README's image build and container setup steps.

## 5. Bind a workspace

When the everyday working directory differs from the configuration directory, run this command from the working directory:

```bash
rigyard init -f examples/robot-development/rigyard.yaml
robot validate
```

The binding applies to that directory and all of its descendants. Rigyard searches upward for the
nearest `.rigyard/context.yaml`, so nested workspaces remain independent. This example configures
`workspace.command_alias: robot`. Initialization installs a generic `robot` command in Rigyard's
command directory, which must be on `PATH`. The command discovers the workspace at runtime and can
be shared by multiple workspaces. A CLI option can override or disable it:

```bash
rigyard init -f examples/robot-development/rigyard.yaml --alias xxxbot
xxxbot validate
rigyard init -f examples/robot-development/rigyard.yaml --no-alias --force
```

Remove the configured alias when it is no longer needed:

```bash
rigyard alias remove
```

Continue with the [configuration overview](configuration/index.md) or select a [core feature](index.md#core-features).
