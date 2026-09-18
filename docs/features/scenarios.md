# 场景启动

场景用于在 Docker 容器中启动开发和调试进程。Toolchain 固定使用 tmux 作为场景入口，不支持 supervisord 或生产部署编排。容器可以提前创建，也可以由场景引用的 Docker Compose 文件创建。

| 层级 | 含义 | tmux 映射 |
| --- | --- | --- |
| scenario | 一次调试启动单元 | session |
| instance | 一个容器中的一套软件系统 | window |
| group | 一个容器内调试进程 | pane |

## 已有容器模式

```yaml
robot-system:
  description: Robot development stack
  instances:
    robot1:
      description: Primary robot
      container: robot-development
      groups:
        drivers:
          setup: [/opt/ros/humble/setup.bash, install/setup.bash]
          command: [ros2, launch, robot_bringup, drivers.launch.py]
          interpreter: [/bin/bash, -eo, pipefail]
          workdir: /workspace
          environment:
            ROS_DOMAIN_ID: "7"
        navigation:
          script: /workspace/scripts/navigation.sh
          interpreter: [/bin/bash, -eo, pipefail]
  profiles:
    development:
      restart_container: always
      attach: true
      stop_grace_seconds: 5
      mouse: true
      keep_alive: true
```

没有 `compose` 时，每个 instance 必须使用 `container` 指向已有容器名称或 ID。目标不存在或无法按 profile 策略启动时，场景启动失败，不会自动切换到 Compose。

## Compose 模式

```yaml
robot-system:
  compose:
    file: deploy/compose.development.yaml
    project_name: robot-system-debug
    wait_timeout_seconds: 60
    environment:
      WORKSPACE: ${WORKSPACE_ROOT}
  instances:
    robot1:
      service: robot
      groups:
        drivers:
          script: /workspace/scripts/drivers.sh
  profiles:
    development:
      attach: true
```

配置 `compose` 后，每个 instance 必须使用 `service` 指向 Compose service，不能使用 `container`。`scene start` 执行 `docker compose up -d --wait`，然后通过 `docker compose ps -q` 将每个 service 解析为唯一容器 ID；当前不支持一个 instance 对应多个副本。

`compose.file` 相对于根 manifest 解析。`compose.environment` 会在工具链模板解析后作为 Compose 插值环境传给 `config`、`up`、`ps` 和 `down`，并覆盖同名宿主环境变量：

```yaml
# scenario source
compose:
  file: deploy/compose.yaml
  environment:
    WORKSPACE: ${WORKSPACE_ROOT}
```

```yaml
# compose.yaml
services:
  robot:
    volumes:
      - "${WORKSPACE}:/workspace"
```

dry-run 只显示变量名，不显示变量值。

## scenario 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | 菜单说明 |
| `compose` | mapping | 否 | — | Compose 生命周期配置 |
| `instances` | mapping | 是 | — | 至少一个 instance |
| `profiles` | mapping | 是 | — | 至少一个 profile |

## Compose 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `file` | path | 是 | — | Compose YAML，基于根 manifest |
| `project_name` | string | 否 | 稳定生成 | Compose project name |
| `wait_timeout_seconds` | integer | 否 | `60` | 1～3600 秒 |
| `environment` | string mapping | 否 | `{}` | Compose 插值环境 |

## instance 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | instance 说明 |
| `enabled` | boolean | 否 | `true` | 是否默认选择 |
| `container` | string | 条件 | — | 已有容器模式目标 |
| `service` | string | 条件 | — | Compose 模式目标 |
| `groups` | mapping | 是 | — | 至少一个 group |

instance 名成为 tmux window 名，必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*`。`.` 和 `:` 会与 tmux target 语法冲突，因此不允许。

## group 字段

每个 group 必须使用 `script` 或 `command`，两者互斥：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | group 说明 |
| `enabled` | boolean | 否 | `true` | 是否启动 |
| `script` | string | 条件 | — | 容器内脚本路径 |
| `command` | string list | 条件 | — | 直接执行的 argv |
| `setup` | string list | 否 | `[]` | 依次 source 后执行进程 |
| `interpreter` | string list | 否 | `[/bin/sh, -eu]` | 执行 setup/script 的解释器 |
| `user` | string | 否 | 容器默认用户 | `docker exec --user` |
| `workdir` | string | 否 | 容器默认目录 | 容器绝对工作目录 |
| `environment` | string mapping | 否 | `{}` | group 环境变量 |

ROS 的 `setup.bash` 通常要求 bash，且可能不兼容 `set -u`，因此建议显式使用：

```yaml
interpreter: [/bin/bash, -eo, pipefail]
```

## profile 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `session` | string | 否 | 稳定生成 | tmux session 名 |
| `attach` | boolean | 否 | `true` | 启动后 attach |
| `replace` | boolean | 否 | `true` | 替换同名场景 tmux 对象 |
| `stop_grace_seconds` | integer | 否 | `5` | 发送 Ctrl+C 后等待 0～30 秒 |
| `restart_container` | enum | 否 | `always` | 已有容器生命周期策略 |
| `mouse` | boolean | 否 | `true` | tmux mouse |
| `keep_alive` | boolean | 否 | `true` | group 退出后保留可操作 shell |

`restart_container` 只用于已有容器模式：

| 值 | 行为 |
| --- | --- |
| `always` | 运行中执行 restart，停止时执行 start |
| `if_not_running` | 运行中不处理，停止时执行 start |
| `never` | 不改变生命周期，只接受已经运行的容器 |

## 参数解析

profile、instance/group 的 `enabled` 和 instance 目标会先解析；只有被选中 instance 中启用的 group 才继续解析进程字段。所有 Runtime 字段支持相应类型的[运行时参数](../configuration/runtime-values.md)，字符串支持[模板](../configuration/templates.md)。

默认选择所有 `enabled: true` 的 instance。`--instance NAME` 可重复使用，仅启动、停止或查询指定 window：

```bash
toolchain scene start robot-system development --instance robot1
toolchain scene stop robot-system development --instance robot1
```

场景只有一个 profile 时可省略 profile 名；存在多个 profile 时必须显式选择。

## tmux 与 keep-alive

每个 pane 开启 `remain-on-exit`。`keep_alive: true` 时：

1. group 进程退出后进入已执行相同 setup 的容器交互 shell。
2. 容器 shell 退出后进入宿主交互 shell。

这便于查看输出、修改命令并重试。设为 `false` 时，进程退出后 pane 变为 dead，只保留输出。进程在启动宽限期内退出仍被视为启动失败，并保留 tmux 对象用于诊断。

## 生命周期边界

| 命令 | tmux | 已有容器 | Compose 容器 |
| --- | --- | --- | --- |
| `scene start` | 创建 session/window/pane | 按 restart 策略处理 | `compose up -d --wait` |
| `scene stop` | 停止进程并关闭目标 | 保留 | 保留 |
| `scene down` | 停止完整场景 | 不适用 | `compose down` |

`scene down` 只适用于 Compose 场景，并以完整 Compose project 为边界，因此不接受 `--instance`。Compose up 后若后续解析或 tmux 创建失败，容器会保留以便诊断；需要清理时显式执行 `scene down`。

## 命令

```bash
toolchain scene start robot-system development
toolchain scene start robot-system --dry-run --no-attach
toolchain scene status robot-system development
toolchain scene attach robot-system development --instance robot1 --group drivers
toolchain scene logs robot-system development --instance robot1 --group drivers
toolchain scene logs robot-system development --follow
toolchain scene stop robot-system development
toolchain scene down robot-system development
```

`attach` 和指定 group 的 `logs` 需要能够唯一定位 instance；多 instance 场景应同时传入 `--instance`。停止时先向 pane 发送 Ctrl+C，等待 `stop_grace_seconds` 后关闭对应 tmux 对象。
