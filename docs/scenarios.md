# 场景启动

场景功能将“运行哪些进程”和“如何托管进程”分离：公共 `groups` 描述容器内脚本，profile 选择开发用 tmux 或部署用 Docker Compose + supervisord。

## 配置

根 manifest 引用独立场景文件：

```yaml
sources:
  scenarios: config/scenarios.yaml
```

场景结构：

```yaml
robot-system:
  groups:
    navigation:
      enabled: true
      container: robot-development
      service: robot
      script: /workspace/scripts/scenarios/navigation.sh
      interpreter: [/bin/bash, -euo, pipefail]
      workdir: /workspace
      environment:
        ROS_DOMAIN_ID: "7"
      supervisor:
        priority: 20
        autorestart: unexpected
        stopsignal: INT
        stopasgroup: true
        killasgroup: true
        stopwaitsecs: 15
  profiles:
    development:
      backend: tmux
      attach: true
      replace: false
      stop_grace_seconds: 5
    deployment:
      backend: compose-supervisor
      compose_file: deploy/compose.yaml
      project_name: robot-system
      supervisor_config_dir: deploy/generated/supervisor
```

`script` 是容器内路径。建议脚本最后使用 `exec ros2 launch ...`，使进程能够直接收到 tmux 或 supervisord 转发的停止信号。

## tmux 开发模式

tmux 始终在宿主机运行，窗口通过 `docker exec -it` 执行容器内脚本。

开发 profile 可配置 Compose，公共 groups 的格式保持不变：

```yaml
development:
  backend: tmux
  compose_file: deploy/compose.development.yaml
  project_name: robot-system-development
  wait_timeout_seconds: 60
  attach: true
```

此模式每个启用的 group 必须指定 `service`，其值是 Compose 文件 `services` 下的名称。
工具链按 service 查找实际容器 ID；`container` 字段在此模式不参与定位。一个 service 必须
对应一个运行中的容器，多个 group 可共用同一个 service。

启动时先验证 Compose 配置及目标服务，停止该场景的旧 tmux session，再对目标服务执行
`docker compose stop` 和 `docker compose up -d --wait --wait-timeout 60`。无容器时会创建，
已有容器会先停止再启动；配置变化时 Compose 可重新创建容器。`--wait` 在有健康检查时等待
健康检查通过，否则等待容器运行。设备或 ROS 层的 readiness 仍应由启动脚本检查。
要求 Docker Compose v2 支持 `up --wait --wait-timeout`。

开发 Compose 应运行持续存活的基础进程，例如 `exec sleep infinity`，由 tmux 执行 groups；
不能同时用 supervisord 自动启动同一批节点，否则会重复启动。参考
`examples/deploy/compose.development.yaml`，部署仍使用原有 Compose + supervisord 文件。
停止再启动不会清空容器可写层，不执行 `down`，不删除 volumes。

Compose 模式启动会自动替换当前场景的旧 tmux session，无需 `replace: true`。
`scene stop` 只停止启动项并关闭 session，保留容器；`status/attach/logs` 不重启容器。
Compose 启动或健康检查失败时不会创建窗口，保留容器现场用于诊断；窗口创建失败时清理
本次新建的 session。停止旧 session 或容器的操作不会自动回滚。

不配置 `compose_file` 时，保持原有连接已有容器的方式：每个 group 必须填写 `container`。
Toolchain 在宿主机执行预检，确认 tmux、Docker 和所有目标容器可用。每个启用的 group 对应一个开启 `remain-on-exit` 的 tmux window，窗口命令为结构化生成的 `docker exec -it`。节点异常退出后窗口仍然保留，可查看退出码和日志。

连接已有容器的模式下，同名 session 默认报错，不会终止现有调试现场。只有 profile 的 `replace: true` 或 CLI 的 `--replace` 才会替换。停止时先向每个窗口发送 `Ctrl+C`，等待 `stop_grace_seconds` 后再关闭 session。

```bash
toolchain scene start robot-system development
toolchain scene start robot-system development --no-attach
toolchain scene attach robot-system development --group navigation
toolchain scene logs robot-system development --group navigation
toolchain scene status robot-system development
toolchain scene stop robot-system development
```

在已有 tmux 内调用 attach 时使用 `switch-client`，否则使用 `attach-session`。

## Compose + supervisord 部署模式

Toolchain 按 `service` 聚合 groups，并在 `supervisor_config_dir` 下生成 `<service>.conf`。Compose 文件必须把对应文件挂载到该 service 的 supervisord include 目录，并以前台模式运行 supervisord：

```yaml
services:
  robot:
    image: example/robot-development:latest
    command: [/usr/bin/supervisord, -n, -c, /etc/supervisor/supervisord.conf]
    volumes:
      - ./generated/supervisor/robot.conf:/etc/supervisor/conf.d/toolchain.conf:ro
```

生成的 program 默认使用 `autorestart=unexpected`、`stopsignal=INT`、`stopasgroup=true` 和 `killasgroup=true`，保证 ROS launch 及子进程尽可能优雅退出。日志发送到容器 stdout/stderr，由 `docker compose logs` 或外部日志系统读取。

```bash
toolchain scene start robot-system deployment
toolchain scene status robot-system deployment
toolchain scene logs robot-system deployment --group navigation --follow
toolchain scene stop robot-system deployment
```

部署模式的日志来自 Docker Compose。`--group` 会选择该 group 所属的 Compose service；同一 service 内有多个 supervisord program 时，输出仍会交错，生产环境应由日志系统按进程字段进一步区分。

`priority` 只保证启动顺序，不代表服务已经就绪。需要等待设备、端口、ROS service 或 lifecycle 状态时，应在工程脚本中实现明确的 readiness 检查。

## 参数解析和失败语义

场景选择分两步解析：先解析被选 profile 和各 group 的 `enabled`，再只解析启用 group 的其他字段。因此 development 不会要求 deployment 参数，被禁用 group 也不会产生无关问题。`stop/status/attach/logs` 不解析脚本和进程环境等仅启动时使用的 group 字段。

启动前的预检或窗口创建失败会清理本次新建的 tmux session；节点启动后自行退出则保留窗口。Compose 启动失败会保留已生成配置用于诊断。所有子进程都通过 argv runner 启动；tmux 要求单个 shell-command 时，由 provider 使用严格 shell quoting 生成。
