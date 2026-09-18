# 全局变量与字符串模板

模板用于配置中的字符串和路径。它在运行时参数选定之后执行，每个字符串只展开一次。

## 内置表达式

| 表达式 | 值 |
| --- | --- |
| `${WORKSPACE_ROOT}` | 当前工作区的宿主机绝对路径 |
| `${TOOLCHAIN_ROOT}` | 实际根 `toolchain.yaml` 所在目录的宿主机绝对路径 |
| `${env:NAME}` | Toolchain 进程的宿主环境变量；不存在时报错 |
| `${date:FORMAT}` | 命令开始时的本地时间 |
| `${utcdate:FORMAT}` | 同一个时间点的 UTC 时间 |
| `${NAME}` | 根 manifest 中的 `variables.NAME` |
| `$${...}` | 输出字面量 `${...}`，不求值 |

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
  CONTAINER_PROJECT_ROOT: /workspace/project

# source 文件
development:
  image: robot/app:${date:%Y%m%d}
  name: dev_${env:USER}_${date:%Y%m%d%H%M}
  mounts:
    - ${PROJECT_ROOT}:${CONTAINER_PROJECT_ROOT}
```

## 路径变量的语义

`WORKSPACE_ROOT` 与 `TOOLCHAIN_ROOT` 是 Toolchain 能够确定的宿主机值：

- 通过 `toolchain init` 绑定时，`WORKSPACE_ROOT` 是执行初始化的目录。
- 直接使用 `--config` 或当前目录 `toolchain.yaml` 时，`WORKSPACE_ROOT` 是当前目录。
- `TOOLCHAIN_ROOT` 始终是实际根配置文件的父目录。

Toolchain 不定义也不推断 `PROJECT_ROOT`。工程结构属于用户语义，应显式配置：

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
```

内置根变量描述宿主文件系统。由于 Toolchain 无法预知 Docker 挂载，容器内路径也必须由用户定义：

```yaml
variables:
  CONTAINER_WORKSPACE_ROOT: /workspace
  CONTAINER_PROJECT_ROOT: /workspace/src/robot
```

## 用户变量

变量名匹配 `[A-Za-z_][A-Za-z0-9_]*`。变量按声明顺序解析，可引用：

- `WORKSPACE_ROOT`、`TOOLCHAIN_ROOT`
- 前面已经声明的用户变量
- `${env:...}`
- `${date:...}`、`${utcdate:...}`

```yaml
variables:
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
  CONFIG_ROOT: ${PROJECT_ROOT}/config
```

不允许前向引用，因此以下配置无效：

```yaml
variables:
  CONFIG_ROOT: ${PROJECT_ROOT}/config
  PROJECT_ROOT: ${TOOLCHAIN_ROOT}/..
```

用户定义同名变量会覆盖 `WORKSPACE_ROOT` 或 `TOOLCHAIN_ROOT`。除非确实需要改变这两个名称的语义，否则不建议覆盖。

## 日期格式

日期使用受限的 `strftime` 格式，例如：

| 指令 | 含义 |
| --- | --- |
| `%Y` | 四位年份 |
| `%m` | 两位月份 |
| `%d` | 两位日期 |
| `%H` | 小时 |
| `%M` | 分钟 |
| `%S` | 秒 |
| `%z` | UTC 偏移 |
| `%%` | 字面量 `%` |

同一条命令只采集一次时间，因此不同字段生成的时间戳保持一致。

## 展开范围

模板会递归处理所选操作中的：

- 字符串和路径
- list/tuple 中的字符串和路径
- mapping 的值
- PromptValue 最终解析出的值
- PromptValue 的静态 `options`

模板不会处理：

- mapping 键
- image、container、build、scenario 等定义名称
- prompt 的 `message`、动态 source 配置
- 替换结果中再次出现的模板

例如宿主环境变量 `VALUE='${date:%Y}'` 时，`${env:VALUE}` 的结果仍是字面量 `${date:%Y}`。

## 环境变量的两种写法

普通字符串模板：

```yaml
name: dev_${env:USER}
```

容器和 hook 的环境字段还支持结构化引用：

```yaml
environment:
  DISPLAY: {env: DISPLAY}
  OPTIONAL_TOKEN: {env: TOKEN, default: ""}
```

两者区别：

- `${env:NAME}` 可以出现在任意受支持字符串中，结果可能显示在计划和错误消息里。
- `{env: NAME, default: ...}` 只用于支持它的容器环境字段，并保留敏感值脱敏语义。

不要使用普通字符串模板传递需要自动脱敏的 secret。

## 校验规则

- 环境变量名必须匹配 `[A-Za-z_][A-Za-z0-9_]*`。
- 不支持 `${env:${NAME}}` 等嵌套表达式。
- 不支持未知模板 kind。
- 模板不能未闭合，结果不能包含 NUL 字节。
- `toolchain validate` 检查语法，但不会读取 `${env:NAME}`。
- 只有实际执行选中配置时，缺失的环境变量才会报错。
