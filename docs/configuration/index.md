# 配置总览

Toolchain 使用 Schema v3。根 `toolchain.yaml` 是 manifest，只声明工程元数据、全局变量和各领域配置文件的位置；镜像、容器、编译和场景分别存放在 source 文件中。

```yaml
version: 3

metadata:
  name: robot-development
  description: Robot software development environment

variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}
  CONTAINER_WORKSPACE_ROOT: /workspace

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

至少需要配置一种 source。每种 source 可以是单一路径，也可以是非空路径列表。路径相对于根 manifest 所在目录，而不是当前目录或 source 文件目录。

## 文件职责

| 文件 | 顶层内容 | 文档 |
| --- | --- | --- |
| `toolchain.yaml` | `version`、`metadata`、`variables`、`sources` | [根 manifest](manifest.md) |
| images source | 镜像名称到镜像定义的 mapping | [镜像](../features/images.md) |
| containers source | 容器名称到容器定义的 mapping | [容器](../features/containers.md) |
| builds source | 编译名称到编译定义的 mapping | [工程编译](../features/builds.md) |
| scenarios source | 场景名称到场景定义的 mapping | [场景启动](../features/scenarios.md) |

source 文件可使用保留字段 `description` 作为菜单分组名称：

```yaml
description: Desktop development targets

development:
  image: example/development:latest
  command: [/bin/bash]
```

不同 source 可以声明同名资源。菜单会先让用户选择来源；直接 CLI 必须使用 `--source PATH` 消除歧义。当前不支持递归 include、跨文件继承或覆盖合并。

## 配置发现顺序

Toolchain 按以下优先级选择根 manifest：

1. 全局 `--config/-f PATH`。
2. 当前目录 `.toolchain/context.yaml` 中的工作区绑定。
3. 当前目录 `toolchain.yaml`。

工作区绑定只在当前目录生效，不搜索父目录。详见 [CLI 的工作区初始化](../reference/cli.md#工作区初始化)。

## 路径基准

除非功能文档特别声明，宿主机相对路径都以根 manifest 所在目录为基准：

- source 文件路径
- 镜像 context 和 Dockerfile 片段
- 容器 bind mount source
- 容器 lifecycle hook 脚本
- Compose 文件

build 和 scenario 中的 `script`、`workdir`、`setup` 是容器内路径，不会相对于宿主机配置目录转换。

## 求值过程

执行一个动作时依次完成：

1. 加载并校验根 manifest 和全部 source。
2. 选择本次操作需要的资源子树。
3. 解析该子树的[运行时参数](runtime-values.md)。
4. 展开[全局变量与字符串模板](templates.md)。
5. 进行严格类型和业务约束校验。
6. 生成不可变计划；`--dry-run` 在此停止。
7. 调用 Docker 或 tmux 执行计划。

未选中的资源不会询问运行时参数，也不会读取其中引用的宿主环境变量。

## 验证与排查

```bash
toolchain validate
toolchain inspect --format yaml
toolchain resolve --non-interactive --with-sources
```

- `validate` 检查全部文件、字段和模板语法，但不要求 `${env:NAME}` 当时存在。
- `inspect` 列出所有内联 PromptValue。
- `resolve` 解析运行时参数；`--with-sources` 同时显示每个值的来源。
