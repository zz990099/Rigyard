# 容器创建

根 manifest 通过 `sources.containers` 引用容器配置。外部文件顶层直接是命名容器 mapping：

```yaml
development:
  name: robot-development
  image: example/robot-development:latest
  interactive: true
  tty: true
  detach: true
  privileged: false
  devices: [/dev/dri]
  group_add: [video]
  network: host
  ipc: host
  mounts:
    - /tmp/.X11-unix:/tmp/.X11-unix
    - ../:/workspace
    - /dev/bus/usb:/dev/bus/usb
  workdir: /workspace
  environment:
    DISPLAY: {env: DISPLAY}
    DOCKER_USER: {env: USER}
    USER: {env: USER}
  command: [/bin/bash]
```

常用命令中的 `development` 是这个 mapping 的键：

```bash
toolchain container create development
```

默认 `interactive`、`tty`、`detach` 均为 true，对应 `docker run -itd`；当前版本要求 `detach: true`。`environment` 可以是固定字符串，也可以通过 `{env: NAME, default: optional}` 从宿主环境读取。

任意支持运行时输入的字段都可以将固定值替换为内联 prompt：

```yaml
privileged:
  default: false
  prompt: {mode: confirm, message: "Enable privileged mode?"}
```

## 挂载

每项格式为 `SOURCE:TARGET[:ro|rw]`：

- `/absolute:/target`、`../relative:/target` 和 `~/home:/target` 是 bind mount。
- `cache:/target` 是 named volume。
- 相对 bind source 以根 `toolchain.yaml` 所在目录为基准。
- target 必须是绝对路径，同一 target 不能重复。

mounts 也可以使用重复输入：

```yaml
mounts:
  default: ["../:/workspace"]
  prompt:
    mode: input
    repeat: true
    message: Enter a mount
    item_hint: SOURCE:TARGET[:ro]
```

`--dry-run` 和正式执行都会完成取值、严格类型校验、宿主环境解析和挂载规范化。dry-run 在计划生成后停止，正式命令将计划转换为无 shell 的 Docker argv。

