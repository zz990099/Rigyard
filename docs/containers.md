# 容器创建

容器配置位于 `containers.<name>`。常用命令中的 `development` 是配置名称：

```bash
toolchain container create development
```

## 配置字段

```yaml
containers:
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

默认 `interactive`、`tty`、`detach` 均为 true，对应 `docker run -itd`。当前版本要求 `detach: true`。`environment` 可写固定字符串，也可用 `{env: NAME, default: optional}` 从宿主环境读取；宿主变量缺失且没有默认值时，计划阶段失败。

任意支持运行时输入的字段都可以把固定值替换为内联 prompt，例如：

```yaml
privileged:
  default: false
  prompt: {mode: confirm, message: "Enable privileged mode?"}
```

## 挂载

每项格式为 `SOURCE:TARGET[:ro|rw]`：

- `/absolute:/target`、`../relative:/target`、`~/home:/target` 是 bind mount。
- `cache:/target` 是 named volume。
- 相对 bind 源以工具链配置文件所在目录为基准。
- target 必须是绝对路径，同一 target 不能重复。

可将 mounts 配置成重复输入：

```yaml
mounts:
  default: ["../:/workspace"]
  prompt:
    mode: input
    repeat: true
    message: Enter a mount
    item_hint: SOURCE:TARGET[:ro]
```

## 预览和执行

```bash
toolchain container create development --dry-run
toolchain container create development
```

两者都会完成取值、严格类型校验、环境变量解析和挂载规范化。`--dry-run` 在计划生成后停止；正式命令把计划转换为无 shell 的 Docker argv，并返回容器 ID。

