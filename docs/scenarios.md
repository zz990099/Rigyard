# 场景启动

场景把“运行哪些进程”和“如何托管进程”分开。一个场景由若干 `instances` 组成，每个 instance
是一套运行在**一个容器**里的软件系统；instance 下的 `groups` 描述容器内要运行的进程。于是：

| 层级 | 含义 | tmux（开发） | compose-supervisor（部署） |
| --- | --- | --- | --- |
| 场景 | 一次启动单元 | 宿主机上一个 tmux session | 一个 Compose project |
| instance | 一套软件系统 / 一个容器 | 一个 window | 一个 Compose service |
| group | 一个容器内进程 | window 下的一个 pane | 一个 supervisord program |

这样“两套系统跑在两个容器里”是结构问题而不是约束问题：加一个 instance 就多一个 window
（或多一份 supervisord 配置）。

## 配置

根 manifest 引用独立场景文件：

```yaml
sources:
  scenarios: config/scenarios.yaml
```

场景结构：

```yaml
robot-system:
  description: Robot software stack
  instances:
    robot1:
      description: Primary robot
      container: robot-development      # tmux 模式的目标容器，必须提前创建
      service: robot                    # compose 模式下的 service 名
      groups:
        drivers:
          setup: [/opt/ros/humble/setup.bash, install/setup.bash]
          command: [ros2, launch, nhybot_bringup, drivers.launch.py]
          workdir: /ros2_ws
          environment:
            ROS_DOMAIN_ID: "7"
          supervisor:
            priority: 10
        navigation:
          script: /workspace/scripts/scenarios/navigation.sh
          interpreter: [/bin/bash, -euo, pipefail]
          workdir: /workspace
          supervisor:
            priority: 20
            stopsignal: INT
            stopasgroup: true
            killasgroup: true
  profiles:
    development:
      backend: tmux
      restart_container: always
      attach: true
      stop_grace_seconds: 5
    deployment:
      backend: compose-supervisor
      compose_file: deploy/compose.yaml
      project_name: robot-system
      supervisor_config_dir: deploy/generated/supervisor
```

每个 group 用 `script` 或 `command` 描述容器内要运行的进程，二者只能选一个：

- `script`：容器内脚本路径，配合 `interpreter`（默认 `[/bin/sh, -eu]`）执行。
- `command`：直接给定的 argv，不经过 shell。
- `setup`：可选的容器内 setup 脚本列表，按顺序 source 后再 `exec` 上面的进程，适合 ROS 的
  `source install/setup.bash`。生成的命令是 `interpreter -c '. A && . B && exec C'`。

两种后端复用同一份定义：tmux 用它生成 pane 命令，supervisord 用它生成 `command=`。建议脚本
最后使用 `exec ros2 launch ...`，使进程能够直接收到 tmux 或 supervisord 转发的停止信号。

`container` 与 `service` 都属于 instance：同一份配置可以同时提供两者，分别给 tmux 和 compose
profile 用。instance 名会成为 tmux window 名，因此必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*`
（`.` 和 `:` 会和 tmux target 语法冲突）。

## 选择 instance

默认启动所有 `enabled: true` 的 instance。`--instance NAME` 可重复，用来只启停或只查看其中几个：

```bash
toolchain scene start robot-system development --instance robot2
toolchain scene stop  robot-system development --instance robot1
toolchain scene logs  robot-system development --instance robot1 --group navigation
```

显式选择一个 `enabled: false` 的 instance 会报错，而不是静默跳过。instance 的 `enabled` 和
group 的 `enabled` 一样支持内联运行时值（`default + prompt`）。

## tmux 开发模式

一个场景对应宿主机上的一个 tmux session，一个 instance 一个 window，一个 group 一个 pane。
窗口和窗格切换：

- 同一 window 内不同组：`Ctrl+b` + 方向键，`Ctrl+b o`（下一个），`Ctrl+b z`（放大当前 pane）
- 跨 window 不同 instance：`Ctrl+b` + 数字，`Ctrl+b n` / `p`，`Ctrl+b w`（列表）
- 鼠标：默认开启（profile 里 `mouse: false` 可关闭），直接点击 pane 或 status bar 即可切换

每个 pane 开启 `remain-on-exit`，节点异常退出后 pane 保留，可查看退出码和日志；pane 标题是
group 名，窗口顶部通过 `pane-border-status` 显示 `序号: 组名`。

`keep_alive`（默认 `true`）让 pane 在进程退出后仍然是可操作的终端。pane 实际运行一个宿主机侧
包装脚本，它忽略 `SIGINT`（否则 `Ctrl+C` 会杀掉 pane 顶层的 `docker exec` 客户端，pane 立刻变
dead，容器内的兜底逻辑根本没机会执行），然后：

1. 运行 group 进程；
2. 无论进程是正常退出、失败还是被 `Ctrl+C` 打断，都打印
   `[toolchain] <group> exited with code <N>`；
3. 执行 `docker exec -it <container> <interpreter[0]> -i`，把 pane 交给**容器内**的交互式 shell
   （例如 `/bin/bash -i`），可以直接查看现场或手动重跑命令。

设为 `false` 时恢复旧行为：进程退出即 pane 变 dead，只能看不能输入。

pane 与 group 的对应关系记录在 tmux pane 选项 `@tc_group` 里，而不是 pane 标题——交互式 shell
会改写标题，只有 pane 选项能保证 `scene logs --group`、`scene attach --group` 和窗口顶部的
`序号: 组名` 边框在进程退出、shell 接管之后依然指向正确的 group。

启动阶段仍会检查两种失败：pane 立刻变成 dead（例如 `docker exec` 本身失败、解释器不存在）
或命令在启动瞬间就退出并打印了上面的 marker，都会报错并保留 session 用于诊断。进程在启动之后
才退出时不再让命令失败，而是留在 pane 的 shell 里等待处理。

启动流程固定为：校验 tmux 与 Docker → 关闭本场景已存在的窗口 → 按 `restart_container`
逐个处理 instance 的目标容器 → 确认容器正在运行 → 逐 instance 建 window、逐 group 建 pane
→ 必要时 attach。顺序不能颠倒：重启容器会终止容器内的所有 `docker exec` 进程，旧窗口必须
先关掉。

`restart_container` 取值：

| 值 | 行为 |
| --- | --- |
| `always`（默认） | 已运行则 `docker restart`，未运行则启动，随后等待容器进入 running |
| `if_not_running` | 已在运行则不动；未运行则启动 |
| `never` | 不改变容器生命周期，只校验其正在运行 |

目标容器不存在时给出可操作错误，提示先用 `toolchain container create` 创建。部分 instance
启动失败会清理本次新建的 session 并报错。

开发 profile 也可以交给 Compose 管理容器（配置 `compose_file`）：

```yaml
development:
  backend: tmux
  compose_file: deploy/compose.development.yaml
  project_name: robot-system-development
  wait_timeout_seconds: 60
  attach: true
```

此模式每个 instance 必须指定 `service`，工具链按 service 查找实际容器 ID，`container` 字段
不参与定位；一个 service 必须对应一个运行中的容器。容器由 Compose 管理，`restart_container`
在此模式不生效（始终 `stop` + `up -d --wait`）。

启动时先验证 Compose 配置及目标服务，停止该场景的旧窗口，再对目标服务执行
`docker compose stop` 和 `docker compose up -d --wait --wait-timeout 60`。无容器时会创建，
已有容器会先停止再启动；配置变化时 Compose 可重新创建容器。`--wait` 在有健康检查时等待
健康检查通过，否则等待容器运行。设备或 ROS 层的 readiness 仍应由启动脚本检查。
要求 Docker Compose v2 支持 `up --wait --wait-timeout`。

开发 Compose 应运行持续存活的基础进程，例如 `exec sleep infinity`，由 tmux 执行 groups；
不能同时用 supervisord 自动启动同一批节点，否则会重复启动。参考
`examples/deploy/compose.development.yaml`，部署仍使用原有 Compose + supervisord 文件。
停止再启动不会清空容器可写层，不执行 `down`，不删除 volumes。

## Compose + supervisord 部署模式

每个 instance 聚合为一个 Compose service，工具链在 `supervisor_config_dir` 下生成
`<service>.conf`，其中的 program 就是该 instance 的 groups。Compose 文件必须把对应文件挂载
到该 service 的 supervisord include 目录，并以前台模式运行 supervisord：

```yaml
services:
  robot:
    image: example/robot-development:latest
    command: [/usr/bin/supervisord, -n, -c, /etc/supervisor/supervisord.conf]
    volumes:
      - ./generated/supervisor/robot.conf:/etc/supervisor/conf.d/toolchain.conf:ro
```

生成的 program 默认使用 `autorestart=unexpected`、`stopsignal=INT`、`stopasgroup=true` 和
`killasgroup=true`，保证 ROS launch 及子进程尽可能优雅退出。日志发送到容器 stdout/stderr，
由 `docker compose logs` 或外部日志系统读取。

```bash
toolchain scene start robot-system deployment
toolchain scene status robot-system deployment
toolchain scene logs robot-system deployment --instance robot1 --group navigation --follow
toolchain scene stop robot-system deployment
```

部署模式的日志来自 Docker Compose：`--instance` 选择 service，`--group` 会选择该 group 所属
的 service；同一 service 内有多个 supervisord program 时输出仍会交错，生产环境应由日志系统
按进程字段进一步区分。

`priority` 只保证启动顺序，不代表服务已经就绪。需要等待设备、端口、ROS service 或 lifecycle
状态时，应在工程脚本中实现明确的 readiness 检查。

## 其他命令

```bash
toolchain scene start robot-system development
toolchain scene start robot-system development --no-attach
toolchain scene attach robot-system development --instance robot1 --group navigation
toolchain scene logs robot-system development --instance robot1 --group navigation
toolchain scene status robot-system development
toolchain scene stop robot-system development
```

`attach` / `logs` 的 `--group` 需要 `--instance` 才能定位（只有一个 instance 时可以省略）。
在已有 tmux 内调用 attach 时使用 `switch-client`，否则使用 `attach-session`。所有 tmux 模式
遇到同名 session 都会自动停止并替换；`replace` 和 `--replace` 保留兼容，不再用于禁止替换。
停止时先向每个 pane 发送 `Ctrl+C`，等待 `stop_grace_seconds` 后再收尾：不带 `--instance`
时关闭整个 session，带 `--instance` 时只关闭对应窗口、保留其他 instance 继续运行。`scene
stop` 只停止启动项，保留容器。

## 参数解析和失败语义

场景选择分三步解析：先解析被选 profile、各 instance 的 `enabled` 和各 group 的 `enabled`，
再只解析被选中 instance 中启用 group 的其余字段。因此 development 不会要求 deployment
参数，被禁用的 instance / group 也不会产生无关问题。`stop/status/attach/logs` 不解析脚本和
进程环境等仅启动时使用的字段。

启动前的预检或窗口创建失败会清理本次新建的 tmux session；节点启动后自行退出则保留窗口。
Compose 启动失败会保留已生成配置用于诊断。所有子进程都通过 argv runner 启动；tmux 要求单个
shell-command 时，由 provider 使用严格 shell quoting 生成。

窗口启动使用独立 argv 执行 `docker exec`，不依赖 tmux 的默认 shell 或 default-command。
每次启动同步当前进程的 PATH、HOME 和 Docker 连接环境，清除 tmux server 中残留的旧配置。
