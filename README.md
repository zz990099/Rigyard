# Toolchain

Toolchain 是一个配置驱动的开发环境工具，当前支持工程编译、分层构建 Docker 镜像、创建开发容器，以及在已有或 Docker Compose 管理的容器中用 tmux 启动命名调试场景。直接 CLI 和交互式菜单共用同一套应用层。

## 安装

要求 Python 3.10+：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

开发环境使用 `pip install -e '.[dev]'`。

## 快速开始

项目默认读取当前目录的 `toolchain.yaml`：

```bash
toolchain                              # 一次性交互菜单
toolchain container create development
toolchain build native
toolchain scene start robot-system development
toolchain image build development
```

`build` 只会在既有且正在运行的容器内执行，不会自动创建容器。

指定其他工程清单：

```bash
toolchain --config examples/toolchain.yaml image build development
toolchain --config examples/toolchain.yaml container create development --dry-run
toolchain --config examples/toolchain.yaml build native --dry-run
toolchain --config examples/toolchain.yaml scene start robot-system development --dry-run
```

`native`、`development` 是外部领域配置中的名称，不是文件路径。

也可以将当前工作目录显式绑定到其他位置的根配置：

```bash
cd /ros2_ws
toolchain init -f src/xbot/.toolchain/toolchain.yaml
toolchain build native
```

`init` 会验证配置并写入当前目录的 `.toolchain/context.yaml`。此后从这个目录运行
`toolchain` 时会使用绑定的配置；工具不会向父目录搜索初始化记录。配置路径解析顺序为：
显式 `--config/-f`、当前目录初始化记录、当前目录 `toolchain.yaml`。位于工作目录内部的配置
会记录为相对路径，便于在宿主机和容器使用不同挂载路径时复用。重复绑定同一配置是幂等的；
改绑其他配置需要 `toolchain init -f PATH --force`。

可以在初始化时生成一个项目级命令别名：

```bash
toolchain init -f src/xbot/.toolchain/toolchain.yaml --alias xxxbot
./xxxbot build native
./xxxbot scene start robot-system development
```

别名是工作区根目录下的可执行脚本，会从脚本自身位置定位已绑定的配置，因此可以从其他目录
调用。它最终仍执行稳定的 `toolchain --config ...` 入口；不会修改 `PATH`，也不会写入
`~/.local/bin`。已有同名文件默认不会覆盖，确认替换时使用 `--force`。

## 工程配置

Schema v3 将根文件作为 manifest。它只保存工具链版本、工程元信息和各领域配置文件的位置：

```yaml
version: 3

metadata:
  name: robot-development
  description: Robot software development toolchain

variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}
  CONTAINER_WORKSPACE_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: /workspace/project

sources:
  images:
    - config/images.yaml
  containers:
    - config/containers.yaml
  builds:
    - config/builds.yaml
  scenarios:
    - config/scenarios.yaml
```

source 路径相对于根 `toolchain.yaml`。`sources.images / containers / builds / scenarios`
都支持数组；每个 source 文件根层级可用保留字段 `description` 作为菜单分组名。不同 source
可以定义同名资源，菜单会先选择来源文件（显示 `description (路径)`），CLI 可用 `--source`
指定来源。至少需要配置一个 source。`variables` 是可选的全局字符串变量，所有领域 source
都可以引用。

编译文件是名称到编译定义的 mapping。toolchain 只在宿主机执行，工程编译统一通过 `docker exec`
进入既有容器运行；工具链不理解 colcon、catkin、CMake 等具体构建系统，只通过明确的解释器 argv
执行工程脚本：

```yaml
native:
  description: Native container build
  container: nhybot_dev_${env:USER}_temp
  script: ${CONTAINER_TOOLCHAIN_ROOT}/scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: ${CONTAINER_WORKSPACE_ROOT}
  setup: [/opt/ros/humble/setup.bash]
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Select build type
        options: [Debug, Release]
```

`container` 必须指向既有、正在运行的容器；`script`、`workdir`、`setup` 都使用容器内路径。
工具链不会创建或启动容器，也不会继承宿主机环境变量。脚本的控制流和具体编译命令由工程维护。

镜像文件是名称到镜像定义的 mapping：

```yaml
development:
  base:
    default: ubuntu:22.04
    prompt:
      mode: select
      message: Select the base image
      options: [ubuntu:22.04, ubuntu:24.04]
  context: .
  tag: example/development:latest
  layers:
    - name: system
      dockerfile: docker/system.Dockerfile
```

容器文件同样是名称到容器定义的 mapping：

```yaml
development:
  image: example/development:latest
  privileged:
    default: false
    prompt:
      mode: confirm
      message: Enable privileged mode?
  mounts:
    default: ["../:/workspace", "cache:/cache:ro"]
    prompt:
      mode: input
      repeat: true
      message: Enter a mount
  workdir: /workspace
  command: [/bin/bash]
```

Dockerfile、构建 context 和相对 bind mount 均以根 `toolchain.yaml` 所在目录为基准，而不是以 source 文件为基准。

## 场景启动

一个场景由若干 instance 组成，每个 instance 是一套跑在容器里的软件系统，instance 下的 group 是容器内的调试进程。启动时在宿主机创建 tmux session：一个 instance 对应一个 window，一个 group 对应一个 pane，并通过 `docker exec -it` 进入容器：

```yaml
robot-system:
  instances:
    robot:
      container: robot-development
      groups:
        drivers:
          setup: [/opt/ros/humble/setup.bash, install/setup.bash]
          command: [ros2, launch, nhybot_bringup, drivers.launch.py]
        navigation:
          script: /workspace/scripts/scenarios/navigation.sh
  profiles:
    development:
      restart_container: always
      attach: true
```

非 Compose 场景中 `container` 属于 instance 且为必填字段，目标容器需提前创建；
`restart_container` 决定启动前如何重启它，默认开启 mouse 与 pane 边框组名。pane 默认像一个
终端：group 进程退出（包括 `Ctrl+C`）后落到已按 `setup` source 过的容器内 shell，`exit` 后再
落到宿主的交互式 shell，pane 不会变成 dead（`keep_alive: false` 可关闭这层包装）。
每个 group 用
容器内 `script`，或 `command` 加可选 `setup`（先 source 再 `exec`）描述进程，两种模式复用
同一套 tmux 启动流程。默认启动全部 `enabled` 的 instance，可用 `--instance NAME` 只启动其中几个；只解析
被选中 instance 中启用 group 的字段，被禁用 instance / group 的其他参数不会被询问。

场景级可选 `compose.file`。配置后，instance 改用 `service` 表示 Compose service 名，
`scene start` 先执行 `docker compose up -d --wait` 并解析对应容器；未配置时仍使用
`container` 表示已有容器名或 ID。
`compose.environment` 可把 `${WORKSPACE_ROOT}` 等工具链模板解析后作为 Compose 插值变量传入。
`scene stop` 只停止 tmux 并保留容器，`scene down` 才停止 tmux 并执行 Compose down。

## 运行时值

固定值直接写在业务字段中。需要运行时取值时，原位置改写为 `default + prompt`，无需顶层参数声明或参数引用。只有执行被选中的镜像、容器、编译入口或场景 profile 时，才会解析相应子树中的运行时值。

| `mode` | 用途 | 约束 |
| --- | --- | --- |
| `input` | 单项输入 | `repeat: true` 时重复输入并返回列表 |
| `confirm` | 是/否确认 | 值为布尔值 |
| `select` | 候选项选择 | 必须设置非空 `options`，或运行时 `source` |

交互模式只负责取值方式，最终数据类型由所在的业务字段校验。

`select` 的候选项可以来自运行时：把 `options` 换成 `source`，工具链只在**真正要询问**时才向
provider 取候选（`--non-interactive`、values 文件、`TOOL_PARAM_*`、`--set` 都不会触发）。内置
provider `docker-containers` 支持用正则 `filter` 过滤名字、`running_only: true` 只看运行中的容器：

```yaml
  container:
    default: nhybot_dev_${env:USER}
    prompt:
      mode: select
      message: Select the build container
      source: {provider: docker-containers, filter: "^nhybot_dev_", running_only: true}
```

候选按行列出（名字列对齐，后面是状态与镜像），最后一行才是问题：

```text
  1) nhybot_dev_binfeng      running, nhybot_base_dev:dev_x86_64_base
  2) nhybot_dev_binfeng_sim  exited, nhybot_base_dev:dev_x86_64_base
Select the build container [nhybot_dev_binfeng]:
```

输入序号选择，也可以直接键入名字（动态候选是开放集合，显式值不做 `options` 白名单校验）。取不到
候选时（docker 不可用、daemon 未启动或过滤后为空）静默回退为普通输入，仍可手输或回车取默认。

显式值优先级从低到高为：

1. 内联 `default`
2. values YAML
3. `TOOL_PARAM_<配置路径>` 环境变量
4. `--set PATH=VALUE`

没有显式来源且启用交互时才询问。即使有默认值也会显示提示，直接回车采用默认值；提示里的默认值
按当前模板上下文渲染后显示（`dev_${env:USER}` 显示为 `dev_root`），回车采用的仍是原默认值，
随后与其它字段一起完成渲染。CI 应使用 `--non-interactive`。

```bash
toolchain container create development \
  --non-interactive \
  --set containers.development.privileged=true \
  --set 'containers.development.mounts=["./:/workspace"]'
```

values 文件是可选的用户输入，并不是工程配置的一部分；结构仍镜像完整运行时路径：

```yaml
images:
  development:
    base: ubuntu:24.04
containers:
  development:
    privileged: true
```

## 字符串模板

运行时字符串和路径支持一个受限的单次模板展开阶段：

```yaml
development:
  image: "robot/app:${date:%Y%m%d}"
  name: "dev_${env:USER}_${date:%Y%m%d%H%M}"
  mounts: ["/home/${env:USER}:/workspace"]
  environment:
    DISPLAY: {env: DISPLAY}
    RUN_ID: "${utcdate:%Y%m%dT%H%M%SZ}"
```

| 模板 | 含义 |
| --- | --- |
| `${env:NAME}` | 读取工具链进程的环境变量；不存在时报错 |
| `${date:FORMAT}` | 按工具链进程的本地时区格式化命令开始时间 |
| `${utcdate:FORMAT}` | 按 UTC 格式化同一个命令开始时间 |
| `${WORKSPACE_ROOT}` | 当前工作区绝对路径，即运行 `toolchain init` 的目录 |
| `${TOOLCHAIN_ROOT}` | 实际 `toolchain.yaml` 所在配置目录的绝对路径 |
| `${NAME}` | 读取根 manifest 的 `variables.NAME` |
| `$${...}` | 输出字面量 `${...}`，不执行模板 |

日期格式采用 `strftime` 指令，例如 `%Y` 年、`%m` 月、`%d` 日、`%H` 时、`%M` 分、
`%S` 秒。同一条命令只采集一次时间，因此多个字段生成的时间戳一致。模板只展开一次：如果
环境变量的内容本身是 `${date:%Y}`，不会继续递归展开。

例如在 `/ros2_ws` 初始化并绑定 `src/xbot/.toolchain/toolchain.yaml` 后，内置参数分别为
`WORKSPACE_ROOT=/ros2_ws` 和
`TOOLCHAIN_ROOT=/ros2_ws/src/xbot/.toolchain`。工作区仍按既有规则仅绑定当前目录，不查找父目录；
直接使用 `--config` 或未初始化时，`WORKSPACE_ROOT` 取当前目录。内置路径不读取同名环境变量，
也不要求工程是 Git 仓库。工具链不再推断 `PROJECT_ROOT`，需要时应显式定义：

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
```

内置根变量描述的是工具链进程看到的宿主文件系统，不能推断 Docker 中的挂载位置。需要容器侧
语义时，应在根 manifest 明确定义，例如：

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
  CONTAINER_WORKSPACE_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: /workspace/src/robot
```

用户变量名匹配 `[A-Za-z_][A-Za-z0-9_]*`。同名用户值覆盖
`${WORKSPACE_ROOT}` 或 `${TOOLCHAIN_ROOT}` 的内置值。变量按 YAML 声明顺序解析，值可以引用
内置变量、前面已经定义的用户变量、`${env:...}` 和日期模板；不允许前向引用，因此循环定义
也会失败。

```yaml
mounts:
  - "${WORKSPACE_ROOT}:/ros2_ws"
  - "${PROJECT_ROOT}:/project"
environment:
  CONFIG_ROOT: "${TOOLCHAIN_ROOT}"
```

模板应用于所选操作中的字符串、路径、字符串列表和最终解析出的 PromptValue；不会展开
mapping 键或配置定义名称。执行所选操作不会读取其他未选配置中的环境模板。
`toolchain validate` 会检查全部模板语法，但不会要求引用的环境变量当时存在。

现有 `{env: NAME, default: optional}` 是容器环境字段的结构化宿主环境引用，继续保留。
`${env:NAME}` 是普通字符串模板，展开值可能出现在计划、错误或命令预览中，不应用来承载
需要自动脱敏的 secret。

## 菜单和命令

菜单只包含：

```text
1) Build image
2) Create container
3) Build project
4) Scene…            → Start scene / Stop scene / Down scene
0) Exit
```

一个动作成功、失败或取消后，进程都会退出，不重新显示一级菜单。配置开发和自动化辅助能力继续保留为直接 CLI：
计划预览后的确认默认是 `[Y/n]`（直接回车即执行），只有创建容器时"同名容器是否删除重建"仍默认
`[y/N]`。

菜单与 CLI 共用一套语义配色（标题、字段名、字段值、成功/警告/错误），并且只在输出流是终端时
生效：默认 `--color=auto`（管道、重定向、CI 日志保持纯文本），可用 `--color=always|never` 强制，
环境变量 `NO_COLOR=1` 或 `TERM=dumb` 同样关闭着色。

计划行是结构化的（`(角色, 文本)` 片段），所以不光是字段名/值，像 `Mount: /a -> /b (bind, rw)`
的箭头、`Window robot: container=… -> …` 里的 `container=`/`->`、动态候选的序号与说明都能各自
着色；运行时提示语也使用同一套角色。

```bash
toolchain validate
toolchain inspect
toolchain resolve --non-interactive
toolchain image build NAME
toolchain container create NAME
toolchain container create NAME --dry-run
toolchain build NAME
toolchain build NAME --dry-run
toolchain scene start SCENE PROFILE
toolchain scene attach SCENE PROFILE --instance NAME --group GROUP
toolchain scene status SCENE PROFILE
toolchain scene logs SCENE PROFILE [--instance NAME] [--group GROUP] [--follow]
toolchain scene stop SCENE PROFILE
toolchain scene down SCENE PROFILE
```

`scene start/stop/status` 都接受可重复的 `--instance NAME`，用于只操作其中几个 instance；
`scene down` 始终作用于完整 Compose project，不接受 `--instance`。

`mounts` 使用 `SOURCE:TARGET[:ro|rw]` 字符串。source 以 `/`、`.` 或 `~` 开头时是 bind mount，否则是 named volume。

## 容器生命周期

容器可以声明创建后的脚本。首次创建时固定按照 `post_create`、`post_start` 的顺序执行：

```yaml
cross-aarch64:
  image: example/cross-aarch64-base:latest
  mounts:
    - .:/workspace
    - /opt/robot/sysroot-aarch64:/opt/sysroot
  lifecycle:
    post_create:
      - name: prepare-sysroot
        script: scripts/cross/prepare-sysroot.sh
        interpreter: [/bin/bash, -eu]
        user: root
        workdir: /workspace
        environment:
          SYSROOT: /opt/sysroot
        timeout_seconds: 300
  command: [/bin/bash]
```

`script` 是相对于根 `toolchain.yaml` 的 UTF-8 文件。工具链在确认前读取并计算 SHA-256，随后通过 stdin 交给 `docker exec -i`，不会调用宿主 shell。hook 失败时命令返回错误，但默认保留已经创建的容器用于诊断。

## 开发

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv build
```

详细设计见 [架构](docs/architecture.md)、[场景启动](docs/scenarios.md)、[工程编译](docs/builds.md)、[CLI 与菜单](docs/cli-menu.md) 和 [容器配置](docs/containers.md)。

## 镜像固定别名

镜像定义可添加可选的 `tag_alias`，支持现有字符串模板和交互参数：

```yaml
base-development:
  base: ubuntu:24.04
  tag: "nhybot_base_dev:dev_x86_64_base_${date:%Y%m%d}"
  tag_alias: "nhybot_base_dev:dev_x86_64_base"
  layers:
    - name: system
      dockerfile: docker/layers/10-system.Dockerfile
```

全部层构建成功后，执行 `docker tag <tag> <tag_alias>`。两个 tag 指向同一镜像，不会
额外构建或复制镜像。后续容器配置的 `image` 可固定填写
`nhybot_base_dev:dev_x86_64_base`。再次成功构建后别名更新，原时间戳 tag 保留。
构建失败时不更新别名；别名标记失败时命令报错，已构建的原 tag 保留。省略该字段保持
原有行为，别名与 tag 相同时不重复执行标记。同一天构建使用相同日期 tag 时仍会覆盖该 tag。
