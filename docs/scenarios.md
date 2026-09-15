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

Toolchain 在宿主机执行预检，确认 tmux、Docker 和所有目标容器可用。每个启用的 group 对应一个开启 `remain-on-exit` 的 tmux window，窗口命令为结构化生成的 `docker exec -it`。节点异常退出后窗口仍然保留，可查看退出码和日志。

同名 session 默认报错，不会终止现有调试现场。只有 profile 的 `replace: true` 或 CLI 的 `--replace` 才会替换。停止时先向每个窗口发送 `Ctrl+C`，等待 `stop_grace_seconds` 后再关闭 session。

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
