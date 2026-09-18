# 容器

容器功能将命名配置转换为显式的 `docker run` 计划，并可在首次创建后执行容器内生命周期 hooks。

## 配置

```yaml
development:
  description: Interactive robot development container
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
    - cache:/cache:ro
  workdir: /workspace
  environment:
    DISPLAY: {env: DISPLAY}
    USER: {env: USER}
    MODE: development
  command: [/bin/bash]
```

## 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | 菜单说明 |
| `image` | string | 是 | — | Docker 镜像引用 |
| `name` | string | 否 | 配置键 | 容器名称 |
| `interactive` | boolean | 否 | `true` | `docker run -i` |
| `tty` | boolean | 否 | `true` | `docker run -t` |
| `detach` | boolean | 否 | `true` | 当前版本只能为 `true` |
| `privileged` | boolean | 否 | `false` | privileged 模式 |
| `devices` | string list | 否 | `[]` | `/host[:/container[:rwm]]` |
| `group_add` | string list | 否 | `[]` | 附加容器 group |
| `mounts` | string list | 否 | `[]` | bind mount 或 named volume |
| `network` | string | 否 | — | Docker network mode/name |
| `ipc` | string | 否 | — | Docker IPC mode |
| `workdir` | string | 否 | — | 容器绝对工作目录 |
| `environment` | mapping | 否 | `{}` | 容器环境变量 |
| `lifecycle` | mapping | 否 | 空 | 创建后的 hooks |
| `command` | string list | 否 | `[]` | 容器命令 argv |

除 `description`、`detach` 和 lifecycle 结构名称外，业务字段均支持相应类型的[运行时参数](../configuration/runtime-values.md)；字符串支持[模板](../configuration/templates.md)。

## 挂载

每项格式为 `SOURCE:TARGET[:ro|rw]`：

- `/absolute:/target`、`../relative:/target`、`~/home:/target` 是 bind mount。
- `cache:/target` 是 named volume。
- 相对 bind source 以根 manifest 所在目录为基准。
- target 必须是容器绝对路径，同一 target 不能重复。
- mode 省略时为 `rw`，只能使用 `ro` 或 `rw`。

```yaml
mounts:
  default: ["../:/workspace"]
  prompt:
    mode: input
    repeat: true
    message: Enter a mount
    item_hint: SOURCE:TARGET[:ro]
```

## 环境变量

固定字符串和模板：

```yaml
environment:
  MODE: development
  RUN_ID: ${utcdate:%Y%m%dT%H%M%SZ}
```

结构化宿主环境引用：

```yaml
environment:
  DISPLAY: {env: DISPLAY}
  OPTIONAL_TOKEN: {env: TOKEN, default: ""}
```

没有 default 且宿主变量缺失时，计划生成失败。结构化引用的值会加入 Docker 错误摘要的脱敏集合。详见[环境变量的两种写法](../configuration/templates.md#环境变量的两种写法)。

## 生命周期 hooks

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

执行顺序固定为：

```text
docker run → post_create（按声明顺序）→ post_start（按声明顺序）
```

| hook 字段 | 必填 | 默认值 | 规则 |
| --- | ---: | --- | --- |
| `name` | 是 | — | 同一 phase 唯一 |
| `script` | 是 | — | 相对根 manifest 的宿主 UTF-8 文件，非空且不超过 1 MiB |
| `interpreter` | 否 | `[/bin/sh, -eu]` | 容器内非空 argv |
| `user` | 否 | — | `docker exec --user` |
| `workdir` | 否 | — | 容器绝对路径 |
| `environment` | 否 | `{}` | 仅注入当前 hook |
| `timeout_seconds` | 否 | `300` | 1～86400 秒 |

脚本内容通过 `docker exec -i ... <interpreter>` 的 stdin 发送，不要求脚本挂载到容器内，也不经过宿主 shell。hook 失败时命令返回执行错误，但保留已经创建的容器以便诊断。hook 应设计为幂等操作。

## 同名容器

创建时如果同名容器已存在，交互模式会询问是否通过 `docker rm -f` 删除并重建，默认回答为 no。拒绝或在非交互模式中遇到同名容器时，本次创建取消。删除容器不会删除挂载的数据卷。

## 命令

```bash
toolchain container create development
toolchain container create development --dry-run
toolchain container create development --source config/containers.yaml
```

`--dry-run` 会完成参数、宿主环境、挂载和 hook 脚本解析，但不调用 Docker。
