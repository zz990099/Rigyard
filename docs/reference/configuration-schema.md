# 配置字段参考

这是 Schema v3 的快速索引。完整语义、示例和失败行为以对应功能文档为准。所有模型都拒绝未知字段。

## 通用类型

| 类型 | 固定值 | 运行时值 |
| --- | --- | --- |
| RuntimeText | string | PromptValue |
| RuntimePath | path string | PromptValue |
| RuntimeBool | boolean | PromptValue |
| RuntimeInteger | integer | PromptValue |
| RuntimeList | string list | PromptValue |
| RuntimeScalar | string/integer/float/boolean | PromptValue |

PromptValue 的字段为 `default` 和必填的 `prompt`。详见[运行时参数](../configuration/runtime-values.md)。

## 根 manifest

| 路径 | 类型 | 默认值 |
| --- | --- | --- |
| `version` | integer，必须为 3 | 必填 |
| `metadata.name` | string | 必填 |
| `metadata.description` | string/null | `null` |
| `variables` | string mapping | `{}` |
| `sources.images` | path/path list/null | `null` |
| `sources.containers` | path/path list/null | `null` |
| `sources.builds` | path/path list/null | `null` |
| `sources.scenarios` | path/path list/null | `null` |

至少一种 source 非空。详见[根 manifest](../configuration/manifest.md)。

## Images source

```text
<image>.description
<image>.base
<image>.context = .
<image>.tag
<image>.tag_alias
<image>.build_args
<image>.layers[].name
<image>.layers[].dockerfile
<image>.layers[].build_args
```

`base`、`tag`、至少一个 layer 为必填项。详见[镜像配置](../features/images.md#字段)。

## Containers source

```text
<container>.description
<container>.image
<container>.name
<container>.interactive = true
<container>.tty = true
<container>.detach = true
<container>.privileged = false
<container>.devices = []
<container>.group_add = []
<container>.mounts = []
<container>.network
<container>.ipc
<container>.workdir
<container>.environment = {}
<container>.lifecycle.post_create = []
<container>.lifecycle.post_start = []
<container>.command = []
```

hook 字段为 `name`、`script`、`interpreter`、`user`、`workdir`、`environment`、`timeout_seconds`。详见[容器配置](../features/containers.md#字段)。

## Builds source

```text
<build>.description
<build>.container
<build>.script
<build>.interpreter = [/bin/sh, -eu]
<build>.workdir
<build>.user
<build>.setup = []
<build>.environment = {}
<build>.timeout_seconds
```

`container` 和 `script` 必填。详见[工程编译](../features/builds.md#字段)。

## Scenarios source

```text
<scenario>.description
<scenario>.compose
<scenario>.instances
<scenario>.profiles
```

Compose 字段：

```text
file
project_name
wait_timeout_seconds = 60
environment = {}
```

instance 字段：

```text
description
enabled = true
container | service
groups
```

group 字段：

```text
description
enabled = true
script | command
setup = []
interpreter = [/bin/sh, -eu]
user
workdir
environment = {}
```

profile 字段：

```text
session
attach = true
replace = true
stop_grace_seconds = 5
restart_container = always
mouse = true
keep_alive = true
```

详见[场景配置](../features/scenarios.md)。

## Source 保留字段

每个 source 顶层可以包含：

```yaml
description: Human-readable source group
```

它不是业务资源，不参与名称冲突。其他顶层键都是对应领域的命名定义。
