# Rigyard examples

The examples are split by purpose:

- [`minimal`](minimal/) is a small first project with one container and one menu task.
- [`robot-development`](robot-development/) is a small Ubuntu 24.04 / ROS Jazzy example
  with two image layers, an interactive development container, a colcon build script,
  and the standard Nav2 TB3 simulation in tmux.

Validate either project without starting Docker:

```bash
rigyard --config examples/minimal/rigyard.yaml validate
rigyard --config examples/robot-development/rigyard.yaml validate
```

Each example has its own README with the commands needed to use it.
