# 架构

## 配置组合

Schema v2 将磁盘配置和应用内配置分开：

```mermaid
flowchart TD
    A[toolchain.yaml manifest] --> B[images source]
    A --> C[containers source]
    B --> D[ToolchainConfig]
    C --> D
    D --> E[选择一个操作子树]
    E --> F[Spec 与执行计划]
```

根 manifest 包含 `version`、`metadata` 和 `sources`。加载器以 manifest 所在目录解析 source 路径，分别校验外部文件，并组装不可变的 `ToolchainConfig`。外部文件错误保留其真实文件、行和列；Dockerfile、context 和 bind mount 则始终相对于 manifest 目录。

当前不支持递归 include、多文件合并或覆盖。后续加入 builds、tests、scenarios 时，可以在 `sources` 下扩展，不改变根配置职责。

## 应用边界

- `config` 负责 manifest、外部 YAML I/O、错误定位和配置组装。
- `parameters` 发现内联 `PromptValue`，按完整路径取值并物化严格模型。
- `images` 与 `containers` 定义模板、严格 Spec、不可变计划和后端协议。
- `application` 选择配置并协调解析与计划。
- `cli` 和一次性 `cli.menu` 共用应用 use case。
- `providers.docker` 只接受已经验证的计划。

运行流程为：

```mermaid
flowchart LR
    A[Template] --> B[ResolvedContext]
    B --> C[ImageSpec / ContainerSpec]
    C --> D[BuildPlan / RunPlan]
    D --> E[Docker Backend]
```

执行某个操作只收集选中子树的 prompts。因此构建 `images.development` 不会询问其他镜像或容器。values 和 overrides 先与全局已知路径比对以捕获拼写错误，再过滤到当前操作。

镜像和容器都先生成完整计划。菜单展示计划并确认后才调用 Docker；命令通过 argv 传给 runner，不经过 shell。

## 容器生命周期

`ContainerRunPlan` 除了 Docker run 参数，还包含已经冻结的 `ContainerHookPlan`。每个 hook 记录阶段、脚本路径和内容、SHA-256、解释器 argv、容器用户、工作目录、环境变量和超时。

创建服务先调用容器 backend，再依次调用 phase-aware hook executor。当前支持：

1. `post_create`：容器首次创建并启动后执行。
2. `post_start`：容器每次启动后执行；当前创建流程也算首次启动，因此排在 `post_create` 之后执行。

目前还没有独立的 start/stop/remove 命令，所以不接受不会被执行的 `pre_stop` 或 `pre_remove` 配置。以后增加相应操作时，可以复用同一个 hook 计划与执行端口。

脚本从工程侧读取并通过 stdin 交给容器解释器，宿主机不执行脚本。hook 失败不回滚 `docker run`，错误会明确说明容器已保留；这让交叉编译环境能够进入容器诊断，同时避免假装跨宿主挂载的修改具有事务性。
