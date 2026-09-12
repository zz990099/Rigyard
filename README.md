# Toolchain

Toolchain 是一个配置驱动的开发环境工具。它目前支持分层构建 Docker 镜像，以及从命名配置创建开发容器；同一套应用层同时服务于直接 CLI 和交互式菜单。

## 快速开始

项目默认读取当前目录的 `toolchain.yaml`。直接运行 `toolchain` 进入菜单；自动化或熟悉配置后可直接执行：

```bash
toolchain image build development
toolchain container create development
```

用 `--config` 切换项目配置：

```bash
toolchain --config examples/toolchain.yaml image build development
toolchain --config examples/toolchain.yaml container create development --dry-run
```

`development` 是 `images` 或 `containers` 下的配置名称，不是文件路径。

## 配置

固定值直接写在业务字段中。需要在运行时获取的值使用内联 `default` 和 `prompt`：

```yaml
version: 1

images:
  development:
    base:
      default: ubuntu:22.04
      prompt:
        mode: select
        message: Select the base image
        options: [ubuntu:22.04, ubuntu:24.04]
    tag: example/development:latest
    layers:
      - name: system
        dockerfile: docker/system.Dockerfile

containers:
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

无需顶层 `parameters` 声明，也没有参数引用。只有执行被选中的镜像或容器配置时，才会解析该子树中的运行时值。

### 交互模式

| `mode` | 用途 | 约束 |
| --- | --- | --- |
| `input` | 单项文本输入 | `repeat: true` 时重复输入并返回列表 |
| `confirm` | 是/否确认 | 值为布尔值 |
| `select` | 从候选项中选择 | 必须设置非空 `options` |

交互模式只描述怎样取值。最终的数据类型由值所在的镜像或容器字段模型校验。交互模式默认关闭：普通标量或列表不会询问用户。

### 值来源和优先级

显式值来源从低到高依次为：

1. 内联 `default`
2. values YAML
3. `TOOL_PARAM_<配置路径>` 环境变量
4. `--set PATH=VALUE`

没有显式来源且启用交互时才读取交互输入。即使存在默认值也会询问，直接回车才采用默认值。`--non-interactive` 下不会读取终端；缺少默认值和显式来源时会报错。

values 文件保持与主配置相同的树结构：

```yaml
images:
  development:
    base: ubuntu:24.04
containers:
  development:
    privileged: true
```

命令行使用完整配置路径，值按 YAML 标量或集合解析：

```bash
toolchain container create development \
  --non-interactive \
  --set containers.development.privileged=true \
  --set 'containers.development.mounts=["./:/workspace"]'
```

### 容器挂载

`mounts` 是字符串列表，不使用 `source`/`target` 对象：

```yaml
mounts:
  - /dev:/dev
  - ../:/workspace
  - cache:/cache:ro
```

格式为 `SOURCE:TARGET[:ro|rw]`。`SOURCE` 以 `/`、`.` 或 `~` 开头时解析为 bind mount，否则解析为 named volume；相对 bind 路径相对于配置文件所在目录。

## 命令

```bash
toolchain                              # 交互式菜单
toolchain validate                     # 校验配置结构
toolchain inspect                      # 列出内联运行时值
toolchain resolve --non-interactive    # 解析并校验全部运行时值
toolchain image build NAME             # 构建分层镜像
toolchain container create NAME        # 创建并启动容器
toolchain container create NAME --dry-run
```

镜像层按声明顺序构建，每层以上一层输出为基础，最后一层使用配置的目标 tag。容器固定使用 detached 模式，并默认生成与 `docker run -itd` 对应的参数；`--dry-run` 只展示已经解析、校验和规范化的计划。

## 开发

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

详细设计见 [架构](docs/architecture.md)、[CLI 与菜单](docs/cli-menu.md) 和 [容器配置](docs/containers.md)。
