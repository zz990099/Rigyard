# 根 manifest

根 manifest 的 Schema 版本当前固定为 3，并拒绝未知字段。

```yaml
version: 3
metadata:
  name: robot-development
  description: Optional description
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
sources:
  images: config/images.yaml
  containers:
    - config/containers.yaml
  builds: config/builds.yaml
  scenarios: config/scenarios.yaml
```

## 字段

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | ---: | --- |
| `version` | integer | 是 | 必须是 `3` |
| `metadata` | mapping | 是 | 工程展示信息 |
| `metadata.name` | string | 是 | 去除空白后不能为空 |
| `metadata.description` | string | 否 | 工程说明 |
| `variables` | string mapping | 否 | 默认空；见[模板变量](templates.md) |
| `sources` | mapping | 是 | 至少声明一种领域配置 |
| `sources.images` | path 或 path list | 否 | 镜像 source |
| `sources.containers` | path 或 path list | 否 | 容器 source |
| `sources.builds` | path 或 path list | 否 | 编译 source |
| `sources.scenarios` | path 或 path list | 否 | 场景 source |

source 列表不能为空，所有路径相对于根 manifest 解析。配置文件应使用 UTF-8 YAML。

## 定义名称

镜像、容器、build、scenario、layer 和 group 的定义名称匹配：

```text
[A-Za-z][A-Za-z0-9_.-]*
```

scenario instance 会直接成为 tmux window 名，因此使用更严格的规则：

```text
[A-Za-z0-9][A-Za-z0-9_-]*
```

## 全局变量

变量名匹配 `[A-Za-z_][A-Za-z0-9_]*`，值必须是字符串。它们按 YAML 声明顺序解析：

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
  CONFIG_ROOT: ${PROJECT_ROOT}/config
  CONTAINER_PROJECT_ROOT: /workspace/project
```

允许引用内置变量、宿主环境、日期和前面已经定义的变量；不允许前向引用。完整规则见[全局变量与字符串模板](templates.md)。
