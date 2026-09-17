# 场景启动

场景用于在 Docker 容器中启动开发和调试进程。工具在宿主机使用 tmux 组织进程，容器既可以
提前创建，也可以由场景引用的 Docker Compose 文件创建。场景不负责 supervisord 或生产部署。

| 层级 | 含义 | tmux 映射 |
| --- | --- | --- |
| 场景 | 一次调试启动单元 | 一个 session |
| instance | 一套运行在一个已有容器中的软件系统 | 一个 window |
| group | 容器内的一个调试进程 | 一个 pane |

## 配置

根 manifest 引用独立场景文件：

```yaml
sources:
  scenarios: config/scenarios.yaml
```

场景结构：

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
          command: [ros2, launch, nhybot_bringup, drivers.launch.py]
          workdir: /ros2_ws
          environment:
            ROS_DOMAIN_ID: "7"
        navigation:
          script: /workspace/scripts/scenarios/navigation.sh
          interpreter: [/bin/bash, -euo, pipefail]
          workdir: /workspace
  profiles:
    development:
      restart_container: always
      attach: true
      stop_grace_seconds: 5
      mouse: true
      keep_alive: true
```

每个 instance 必须指定一个已存在的 `container`。instance 名会成为 tmux window 名，因此必须
匹配 `[A-Za-z0-9][A-Za-z0-9_-]*`；`.` 和 `:` 会与 tmux target 语法冲突。

需要由 Compose 准备容器时，在场景级增加 `compose`：

```yaml
robot-system:
  compose:
    file: deploy/compose.development.yaml
    project_name: robot-system-debug  # 可省略，工具会生成稳定名称
    wait_timeout_seconds: 60
  instances:
    robot1:
      container: robot
      groups:
        drivers: {script: /workspace/scripts/scenarios/drivers.sh}
  profiles:
    development: {attach: true}
```

两种模式都保留 `container` 字段：无 `compose` 时它是已有容器的名称或 ID；有 `compose` 时它是
Compose service 名。启动后工具通过 `docker compose ps -q` 将 service 解析为容器 ID。每个
service 必须恰好产生一个容器，因此当前不支持将同一个 instance 映射到多副本 service。
`file` 相对于根 `toolchain.yaml` 解析，而不是相对于场景 source 文件。

每个 group 用 `script` 或 `command` 描述容器内要运行的进程，二者只能选一个：

- `script`：容器内脚本路径，配合 `interpreter`（默认 `[/bin/sh, -eu]`）执行。
- `command`：直接给定的 argv，不经过 shell。
- `setup`：可选的容器内 setup 脚本列表，按顺序 source 后再 `exec` 进程，适合 ROS 的
  `source install/setup.bash`。

## 容器要求

未配置 `compose` 时，场景启动前必须通过 `toolchain container create` 或其他方式准备目标
容器。目标不存在时，启动会失败并给出创建提示，且不会自动退回到 Compose。

`restart_container` 控制启动场景前如何处理已有容器：

| 值 | 行为 |
| --- | --- |
| `always`（默认） | 已运行则 `docker restart`，已停止则 `docker start` |
| `if_not_running` | 已运行则不处理，已停止则 `docker start` |
| `never` | 不改变生命周期，只校验容器正在运行 |

`scene stop` 只停止 tmux 中的调试进程并关闭 window/session，不停止或删除容器，便于继续进入
容器检查现场。

配置 `compose` 时，`scene start` 会运行 `docker compose up -d --wait`。`restart_container`
只适用于已有容器模式，在 Compose 模式下忽略。`scene stop` 仍然只停止 tmux，保留容器和现场；
显式执行 `scene down` 才会先停止 tmux，再运行 `docker compose down`。`down` 以完整 Compose
project 为生命周期边界，不接受 `--instance`。

## tmux 行为

一个场景对应一个 tmux session，一个 instance 对应一个 window，一个 group 对应一个 pane。
窗口和窗格切换：

- 同一 window 内不同组：`Ctrl+b` + 方向键、`Ctrl+b o`、`Ctrl+b z`。
- 跨 window：`Ctrl+b` + 数字、`Ctrl+b n` / `p`、`Ctrl+b w`。
- `mouse: true` 时可以直接点击 pane 或 status bar。

每个 pane 开启 `remain-on-exit`。keep_alive 默认为 true：group 进程退出后打印退出码，并把
pane 交给容器内的交互式 shell，方便查看现场或手动重跑。设为 false 时，进程退出后 pane
变为 dead，只保留输出。

已有容器模式的启动顺序固定为：校验 tmux 与 Docker → 关闭本场景已有 window/session → 按
`restart_container` 处理容器 → 确认容器正在运行 → 创建 window 和 pane → 必要时 attach。
必须先关闭旧 window，因为重启容器会终止其中已有的 `docker exec` 进程。

Compose 模式则先校验 service，再关闭旧 tmux 对象，随后执行 `compose up`、解析容器 ID、确认
容器运行并创建 window/pane。若 `compose up` 后的解析或 tmux 创建失败，容器会保留以便诊断；
需要移除时执行 `scene down`。

## 选择 instance

默认启动所有 `enabled: true` 的 instance。`--instance NAME` 可重复使用：

```bash
toolchain scene start robot-system development --instance robot2
toolchain scene stop robot-system development --instance robot1
toolchain scene logs robot-system development --instance robot1 --group navigation
```

部分启动会加入现有 session，并只创建所选 instance 的 window。部分停止只关闭所选 window。

## 常用命令

```bash
toolchain scene start robot-system development
toolchain scene start robot-system development --no-attach
toolchain scene attach robot-system development --instance robot1 --group navigation
toolchain scene logs robot-system development --instance robot1 --group navigation
toolchain scene status robot-system development
toolchain scene stop robot-system development
toolchain scene down robot-system development
```

`attach` / `logs` 的 `--group` 需要能够唯一定位 instance。存在多个 instance 时应同时提供
`--instance`。在已有 tmux 内 attach 时使用 `switch-client`，否则使用 `attach-session`。

停止时先向 pane 发送 `Ctrl+C`，等待 `stop_grace_seconds` 后关闭 tmux 对象。完整停止关闭
整个 session；指定 `--instance` 时只关闭对应 window。

## 参数解析与失败语义

场景选择先解析 profile、instance/group 的 `enabled` 和目标 `container`，启动时再解析所选
group 的脚本、命令和环境。被禁用或未选择的 instance/group 不会产生无关提示。

启动前检查或 window 创建失败时会清理本次新建的 tmux 对象；节点启动后自行退出时保留 pane
用于诊断。所有进程通过 argv runner 启动，容器内命令使用独立的 `docker exec`，不依赖 tmux
默认 shell。
