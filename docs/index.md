# Rigyard documentation

Rigyard represents image builds, containers, project builds, tests, constrained custom tasks, and multi-process debugging scenarios as version-controlled YAML. It runs on the host and executes explicit plans through Docker and tmux; it does not interpret build or test systems such as colcon, CMake, pytest, or ROS launch.

## Start here

- [Installation and requirements](installation.md)
- [Getting started](getting-started.md)
- [CLI reference](reference/cli.md)
- [Exit codes](reference/exit-codes.md)

## Configuration

- [Configuration overview](configuration/index.md)
- [Root manifest](configuration/manifest.md)
- [Global variables and string templates](configuration/templates.md)
- [Runtime values](configuration/runtime-values.md)
- [Configuration schema reference](reference/configuration-schema.md)

## Core features

- [Images](features/images.md)
- [Containers](features/containers.md)
- [Project builds](features/builds.md)
- [Tests](features/tests.md)
- [Custom tasks](features/tasks.md)
- [Scenarios](features/scenarios.md)

## Project maintenance

- [Architecture](development/architecture.md)
- [Release process](development/releasing.md)
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
