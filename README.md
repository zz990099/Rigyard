# Toolchain

Toolchain 是一个面向容器化机器人软件开发的配置驱动 CLI。它用同一份工程清单组织分层镜像构建、开发容器创建、容器内工程编译，以及由 tmux 管理的多进程调试场景。

## 核心能力

- 按顺序组合 Dockerfile 片段并构建分层镜像。
- 创建可复现的开发容器并执行生命周期 hooks。
- 在已经运行的容器中执行工程编译脚本。
- 在已有容器或 Docker Compose service 中启动 tmux 调试场景。
- 使用全局变量、字符串模板和交互式运行时参数复用配置。
- 通过直接命令或一次性交互菜单使用同一套执行逻辑。

## 要求

- Python 3.10 或更高版本
- Docker；使用 Compose 场景时需要 Docker Compose v2
- 使用场景功能时，宿主机需要安装 tmux，目标容器需要可用的交互 shell

## 安装

项目发布到 PyPI 后，推荐将其作为独立命令行工具安装：

```bash
pipx install robot-toolchain
# 或
uv tool install robot-toolchain
```

当前从源码试用：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

开发环境的安装与测试方式见 [贡献指南](https://github.com/zz990099/toolchain/blob/main/CONTRIBUTING.md)。

## 快速开始

项目默认读取当前目录的 `toolchain.yaml`：

```yaml
version: 3

metadata:
  name: robot-development

variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}
  CONTAINER_WORKSPACE_ROOT: /workspace

sources:
  images: [config/images.yaml]
  containers: [config/containers.yaml]
  builds: [config/builds.yaml]
  scenarios: [config/scenarios.yaml]
```

验证配置并执行功能：

```bash
toolchain validate
toolchain image build development
toolchain container create development
toolchain build native
toolchain scene start robot-system development
```

不带子命令时进入一次性交互菜单：

```bash
toolchain
```

配置位于其他目录时，可以显式指定，也可以绑定当前工作区：

```bash
toolchain --config path/to/toolchain.yaml validate
toolchain init -f path/to/toolchain.yaml --alias xxxbot
./xxxbot build native
```

## 文档

- [入门教程](https://github.com/zz990099/toolchain/blob/main/docs/getting-started.md)
- [安装与系统要求](https://github.com/zz990099/toolchain/blob/main/docs/installation.md)
- [配置总览](https://github.com/zz990099/toolchain/blob/main/docs/configuration/index.md)
- [全局变量与字符串模板](https://github.com/zz990099/toolchain/blob/main/docs/configuration/templates.md)
- [运行时参数](https://github.com/zz990099/toolchain/blob/main/docs/configuration/runtime-values.md)
- [镜像](https://github.com/zz990099/toolchain/blob/main/docs/features/images.md)
- [容器](https://github.com/zz990099/toolchain/blob/main/docs/features/containers.md)
- [工程编译](https://github.com/zz990099/toolchain/blob/main/docs/features/builds.md)
- [场景启动](https://github.com/zz990099/toolchain/blob/main/docs/features/scenarios.md)
- [CLI 参考](https://github.com/zz990099/toolchain/blob/main/docs/reference/cli.md)
- [配置字段参考](https://github.com/zz990099/toolchain/blob/main/docs/reference/configuration-schema.md)
- [退出码](https://github.com/zz990099/toolchain/blob/main/docs/reference/exit-codes.md)

完整示例位于 [`examples/`](https://github.com/zz990099/toolchain/tree/main/examples)。

## License

[MIT](https://github.com/zz990099/toolchain/blob/main/LICENSE)
