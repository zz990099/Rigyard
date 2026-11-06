# Robot development example

A small Ubuntu 24.04 / ROS 2 Jazzy workspace with a layered development image, an
interactive container definition, a colcon build, and one Nav2 TurtleBot3 simulation.

```text
robot-development/
├── rigyard.yaml
├── logo.txt
├── builds/
│   ├── build.yaml
│   └── build.sh
├── containers/
│   └── containers.yaml
├── images/
│   ├── image.yaml
│   └── layers/
│       ├── common.dockerfile
│       └── ros.dockerfile
└── scenarios/
    └── nav2-tb3.yaml
```

`rigyard.yaml` references the four source files. `images/image.yaml` supplies the
`ubuntu:24.04` base; Rigyard adds `FROM` when assembling each Dockerfile fragment.
The common layer installs basic build tools and repository prerequisites. The ROS
layer uses the regular ROS APT repository and installs Jazzy ROS base, colcon, Nav2,
the minimal TB3 simulator and RViz. It does not configure snapshot repositories.

## Check the configuration without Docker

From the repository root:

```bash
cd examples/robot-development
rigyard validate
rigyard resolve --non-interactive
rigyard container create development --dry-run --non-interactive
rigyard build development --dry-run --non-interactive
rigyard scene start nav2-tb3 --dry-run --non-interactive
```

These checks use configured defaults without querying Docker or starting processes.
The scene has one profile, `default`, so the CLI can infer it.

## Build and use the environment

The commands in this section perform real Docker operations. They require Docker;
scene operations also require tmux on the host.

```bash
rigyard image build development
rigyard container create development
rigyard scene start nav2-tb3
```

Container creation offers local images matching `rigyard-example/robot-development:` and
defaults to `rigyard_robot_dev_${USER}` as the container name. The build and scene commands
offer containers matching `rigyard_robot_dev_`; if a different name is used, override the
corresponding container field with `--set`.

The example directory is mounted at `/workspace`, using the manifest's directory
as the host path so it also works with `--config` from another working directory.
Add your own ROS packages under `src/`, then run `rigyard build development`.
`builds/build.yaml` sources Jazzy and runs `/workspace/builds/build.sh`, whose only
build command is `colcon build`. The binary Nav2 demo does not require this build.

The scene runs the [official Jazzy TB3 example](https://docs.nav2.org/jazzy/getting_started/quickstart/quickstart/):

```bash
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

This starts Gazebo, Nav2 and RViz in the selected container, with terminal output
attached through tmux. GUI use requires a Linux X11 session (or XWayland), `DISPLAY`,
permission for the container to access that display, and the configured `/dev/dri`
device on the host. Adjust the display mount or device list for your system.

Stop it with `rigyard scene stop nav2-tb3`. This closes tmux and stops the selected
container after the default 5-second grace period, preserving the container and image.

## Optional project alias

From the example directory, bind the workspace and create the `robot` alias:

```bash
rigyard init -f rigyard.yaml
robot validate
robot scene start nav2-tb3
```

The printed command directory must be writable and on `PATH`. Use `--no-alias` to
bind without an alias, or `--alias NAME` to choose another name. Remove the alias
with `rigyard alias remove`.
