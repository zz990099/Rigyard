# Rigyard examples

The examples are split by purpose:

- [`minimal`](minimal/) is a small first project with one container and one menu task.
- [`robot-development`](robot-development/) is the full reference project. It demonstrates
  workspace initialization, a custom logo, layered images, container lifecycle hooks, native
  builds, tests, custom tasks, tmux scenarios, and a Docker Compose scenario.

Validate either project without starting Docker:

```bash
rigyard --config examples/minimal/rigyard.yaml validate
rigyard --config examples/robot-development/rigyard.yaml validate
```

Each example has its own README with the commands needed to use it.
