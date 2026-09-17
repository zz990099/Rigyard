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

## 生命周期 hooks

交叉编译容器可以复用普通容器创建，仅增加 sysroot 挂载和生命周期配置：

```yaml
cross-aarch64:
  image: example/cross-aarch64-base:latest
  mounts:
    - .:/workspace
    - /opt/robot/sysroot-aarch64:/opt/sysroot
  workdir: /workspace
  lifecycle:
    post_create:
      - name: prepare-sysroot
        script: scripts/cross/prepare-sysroot.sh
        interpreter: [/bin/bash, -eu]
        user: root
        workdir: /workspace
        environment:
          SYSROOT: /opt/sysroot
        timeout_seconds: 300
    post_start:
      - name: verify-toolchain
        script: scripts/cross/verify-toolchain.sh
        timeout_seconds: 30
  command: [/bin/bash]
```

hook 字段：

| 字段 | 含义 |
| --- | --- |
| `name` | 同一 phase 中唯一的 hook 名称 |
| `script` | 相对于根 manifest 的宿主 UTF-8 脚本，最大 1 MiB |
| `interpreter` | 容器内解释器 argv，默认 `[/bin/sh, -eu]` |
| `user` | 可选的容器用户，例如 `root` |
| `workdir` | 可选的容器绝对工作目录 |
| `environment` | 只注入这个 hook 的环境变量 |
| `timeout_seconds` | 1 到 86400 秒，默认 300 |

首次 `container create` 的执行顺序为 `docker run → post_create → post_start`。脚本内容通过 `docker exec -i ... <interpreter>` 的 stdin 发送，不依赖脚本本身已经挂载到容器内，也不经过宿主 shell。

如果 hook 失败，工具链返回退出码 4，给出容器名称、ID、phase 和 hook 名称，并默认保留容器用于检查。脚本应当幂等；敏感环境变量值会从 Docker 错误摘要中隐藏。

固定的编译器、CMake、Ninja 和 pkg-config 应构建进基础镜像。`post_create` 更适合修复已挂载的 sysroot、生成依赖具体挂载路径的 toolchain 文件，而不适合每次重新安装整套固定工具链。

创建时如有同名容器，会提示是否删除并重新创建，默认 `[y/N]`。确认后使用 `docker rm -f`
删除原容器（包括运行中的容器），再创建并运行 lifecycle hooks。不确认或非交互模式下保留
原容器并取消创建。不会删除挂载的数据卷。
