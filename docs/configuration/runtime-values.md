# 运行时参数

任何声明为 Runtime 类型的业务字段，都可以直接填写固定值，也可以在原位置写成 `default + prompt`。不需要单独的顶层参数表。

```yaml
privileged:
  default: false
  prompt:
    mode: confirm
    message: Enable privileged mode?
```

只有执行所选资源时才解析其参数。例如构建 `images.development` 不会询问其他镜像或容器的参数。

## PromptValue 结构

```yaml
default: optional-value
prompt:
  mode: input | confirm | select
  message: Message shown to the user
  options: [one, two]       # 仅静态 select
  source:                   # 或动态 select；与 options 互斥
    provider: docker-containers
    filter: "^robot_"
    running_only: true
  repeat: false             # 仅 input
  item_hint: VALUE          # repeat input 的提示
```

`default` 可省略。省略后，在非交互模式中必须通过 values、环境变量或 `--set` 提供值。

## 模式

| mode | 返回值 | 规则 |
| --- | --- | --- |
| `input` | 输入字符串，或由业务字段进一步转换的值 | `repeat: true` 时返回 list |
| `confirm` | boolean | default 必须是 boolean |
| `select` | 候选项 | 必须提供非空 `options` 或 `source` |

最终类型由字段本身校验。例如 integer 字段的 input 结果会在物化 Spec 时转换并检查范围。

## 静态候选

```yaml
base:
  default: ubuntu:22.04
  prompt:
    mode: select
    message: Select the base image
    options: [ubuntu:22.04, ubuntu:24.04]
```

交互输入和显式值必须匹配静态 options。default 也必须是 options 中的一项。

## 动态候选

内置 provider `docker-containers` 在真正显示问题时查询宿主 Docker：

```yaml
container:
  default: robot_development
  prompt:
    mode: select
    message: Select a build container
    source:
      provider: docker-containers
      filter: "^robot_"
      running_only: true
```

- `filter` 是可选正则表达式，匹配容器名称。
- `running_only` 默认 `false`。
- 动态候选是开放集合；values、环境变量和 `--set` 的显式值不要求出现在查询结果中。
- Docker 不可用或没有候选时，交互模式回退为普通输入。
- 非交互模式或已有显式值时不会查询 provider。

## 值来源和优先级

从低到高：

1. 内联 `default`
2. values YAML
3. `TOOL_PARAM_*` 环境变量
4. `--set PATH=VALUE`
5. 无显式来源且启用交互时，由用户输入

交互模式即使存在 default 也会显示问题，直接回车采用 default。`--non-interactive` 不显示问题；缺少必填值时报错。

### values 文件

values 的结构镜像完整配置路径：

```yaml
images:
  development:
    base: ubuntu:24.04
containers:
  development:
    privileged: true
scenarios:
  robot-system:
    profiles:
      development:
        attach: false
```

```bash
toolchain --values local-values.yaml
toolchain image build development --values local-values.yaml
```

values 文件是用户输入，不是工程 source，也不参与定义合并。

### 环境变量

完整配置路径转成大写，并把非字母数字字符替换为下划线：

```text
containers.development.privileged
→ TOOL_PARAM_CONTAINERS_DEVELOPMENT_PRIVILEGED
```

如果两个参数路径映射到同一个环境变量名，Toolchain 会拒绝配置。

### CLI override

`--set` 可重复使用，值按 YAML scalar/list/mapping 语法解析：

```bash
toolchain container create development \
  --non-interactive \
  --set containers.development.privileged=true \
  --set 'containers.development.mounts=["./:/workspace"]'
```

未知路径会直接报错，避免拼写错误被忽略。

## 与字符串模板的顺序

PromptValue 先确定原始值，再由[字符串模板](templates.md)递归展开，最后进入业务字段校验。因此 default 和显式输入都可以包含模板：

```yaml
name:
  default: dev_${env:USER}
  prompt:
    mode: input
    message: Container name
```

提示中会显示渲染后的默认值；直接回车仍采用原始 default，然后在统一模板阶段展开。
