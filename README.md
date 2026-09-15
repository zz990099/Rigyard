# Toolchain

Toolchain 是一个配置驱动的开发环境工具，当前支持工程编译、分层构建 Docker 镜像，以及从命名配置创建开发容器。直接 CLI 和交互式菜单共用同一套应用层。

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
toolchain build native
toolchain image build development
toolchain container create development
```

指定其他工程清单：

```bash
toolchain --config examples/toolchain.yaml image build development
toolchain --config examples/toolchain.yaml container create development --dry-run
toolchain --config examples/toolchain.yaml build native --dry-run
```

`native`、`development` 是外部领域配置中的名称，不是文件路径。

## 工程配置

Schema v2 将根文件作为 manifest。它只保存工具链版本、工程元信息和各领域配置文件的位置：

```yaml
version: 2

metadata:
  name: robot-development
  description: Robot software development toolchain

sources:
  images: config/images.yaml
  containers: config/containers.yaml
  builds: config/builds.yaml
```

source 路径相对于根 `toolchain.yaml`。当前每个领域最多引用一个 YAML 文件，至少需要配置一个 source。

编译文件是名称到编译定义的 mapping。工具链不理解 colcon、catkin、CMake 等具体构建系统，只通过明确的解释器 argv 执行工程脚本：

```yaml
native:
  description: Native release build
  script: scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: .
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Select build type
        options: [Debug, Release]
```

`script` 和 `workdir` 均相对于根 `toolchain.yaml`。编译脚本直接连接当前终端，不调用隐式宿主 shell；脚本的控制流和具体编译命令由工程维护。

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

## 运行时值

固定值直接写在业务字段中。需要运行时取值时，原位置改写为 `default + prompt`，无需顶层参数声明或参数引用。只有执行被选中的镜像、容器或编译入口时，才会解析该子树中的运行时值。

| `mode` | 用途 | 约束 |
| --- | --- | --- |
| `input` | 单项输入 | `repeat: true` 时重复输入并返回列表 |
| `confirm` | 是/否确认 | 值为布尔值 |
| `select` | 候选项选择 | 必须设置非空 `options` |

交互模式只负责取值方式，最终数据类型由所在的业务字段校验。

显式值优先级从低到高为：

1. 内联 `default`
2. values YAML
3. `TOOL_PARAM_<配置路径>` 环境变量
4. `--set PATH=VALUE`

没有显式来源且启用交互时才询问。即使有默认值也会显示提示，直接回车采用默认值。CI 应使用 `--non-interactive`。

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

## 菜单和命令

菜单只包含：

```text
1) Build image
2) Create container
3) Build project
0) Exit
```

一个动作成功、失败或取消后，进程都会退出，不重新显示一级菜单。配置开发和自动化辅助能力继续保留为直接 CLI：

```bash
toolchain validate
toolchain inspect
toolchain resolve --non-interactive
toolchain image build NAME
toolchain container create NAME
toolchain container create NAME --dry-run
toolchain build NAME
toolchain build NAME --dry-run
```

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

详细设计见 [架构](docs/architecture.md)、[工程编译](docs/builds.md)、[CLI 与菜单](docs/cli-menu.md) 和 [容器配置](docs/containers.md)。
