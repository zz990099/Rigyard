# 工程编译

工程编译统一通过 `docker exec` 在已经存在且正在运行的容器内执行。Toolchain 不创建、启动或拉取 build 使用的容器，也不理解 colcon、catkin、CMake 等具体构建系统。

## 配置

```yaml
native:
  description: Native container build
  container: robot-development
  script: ${CONTAINER_WORKSPACE_ROOT}/scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: ${CONTAINER_WORKSPACE_ROOT}
  user: root
  setup:
    - /opt/ros/humble/setup.bash
    - install/setup.bash
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Select build type
        options: [Debug, Release, RelWithDebInfo]
  timeout_seconds: 3600
```

## 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | 菜单说明 |
| `container` | string | 是 | — | 已有容器名称或 ID |
| `script` | path | 是 | — | 容器内脚本路径 |
| `interpreter` | string list | 否 | `[/bin/sh, -eu]` | 容器内解释器 argv，不能为空 |
| `workdir` | path | 否 | 容器默认目录 | 容器内工作目录 |
| `user` | string | 否 | 容器默认用户 | `docker exec --user` |
| `setup` | string list | 否 | `[]` | 按顺序 source 的容器内脚本 |
| `environment` | string mapping | 否 | `{}` | 仅注入当前 build，不继承宿主环境 |
| `timeout_seconds` | integer | 否 | 无限制 | 1～86400 秒 |

所有业务字段支持相应类型的[运行时参数](../configuration/runtime-values.md)，字符串和路径支持[模板](../configuration/templates.md)。`container` 常配合 `docker-containers` 动态候选使用。

## 执行语义

容器必须已经存在且正在运行；不存在或停止时命令失败，不会改变其生命周期。实际容器内控制流等价于：

```text
. /opt/ros/humble/setup.bash &&
. install/setup.bash &&
exec /bin/bash -euo pipefail /workspace/scripts/build-native.sh
```

解释器、setup、script、workdir 都是容器内值。Toolchain 通过 argv 调用 `docker exec`，不会让宿主 shell 解释业务命令。`environment` 只包含显式配置的覆盖，不会复制整个宿主环境。

`timeout_seconds` 控制宿主上的 `docker exec` client，不保证能够可靠终止容器内已经派生的所有进程。需要严格的进程树超时时，应在 build script 内使用容器侧的 `timeout` 或相应机制。

## 命令

```bash
toolchain build native
toolchain build native --dry-run
toolchain build native --source config/builds.yaml
toolchain build native --non-interactive \
  --set builds.native.environment.BUILD_TYPE=Debug
```

`--dry-run` 会完成容器名、脚本、setup、环境和最终 `docker exec` argv 的计划生成，但不检查或执行 Docker 容器。
