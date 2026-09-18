# 入门教程

本教程使用仓库自带示例展示配置加载与计划预览，不要求实际构建镜像。

## 1. 安装

按照[安装说明](installation.md)安装后确认：

```bash
toolchain --version
```

## 2. 验证示例配置

在仓库根目录运行：

```bash
toolchain --config examples/toolchain.yaml validate
```

根 manifest 引用了四类独立配置：镜像、容器、编译和场景。`validate` 会读取全部 source，检查 YAML、字段类型和模板语法，但不会执行 Docker 命令。

## 3. 查看运行时参数

```bash
toolchain --config examples/toolchain.yaml inspect
```

输出列出配置中的交互参数及其 `TOOL_PARAM_*` 环境变量名。也可以非交互地解析所有参数：

```bash
toolchain --config examples/toolchain.yaml resolve \
  --non-interactive \
  --set images.development.base=ubuntu:24.04
```

## 4. 预览执行计划

以下命令完成配置选择、参数解析和计划生成，但不调用 Docker：

```bash
toolchain --config examples/toolchain.yaml container create development --dry-run
toolchain --config examples/toolchain.yaml build native --dry-run
toolchain --config examples/toolchain.yaml scene start robot-system development --dry-run
```

`image build` 当前没有 dry-run；执行前可先使用 `validate` 和 `resolve` 检查配置与参数。

## 5. 绑定工作区

日常工作目录与配置目录不同时，可在日常工作目录执行：

```bash
toolchain init -f path/to/toolchain.yaml
toolchain validate
```

初始化记录只对当前目录生效，不向父目录搜索。也可以同时生成项目局部命令：

```bash
toolchain init -f path/to/toolchain.yaml --alias xxxbot
./xxxbot validate
```

接下来阅读[配置总览](configuration/index.md)，或直接选择需要的[核心功能](index.md#核心功能)。
