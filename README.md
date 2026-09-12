# toolchain

`toolchain` 是一个配置驱动的通用开发工具链。当前已提供 YAML 声明式参数系统，以及按顺序组合 Dockerfile 片段的分层镜像构建能力。

## 状态与边界

- Schema 只支持 YAML，版本固定为 `1`。
- 运行时要求 Python 3.10+。
- 参数类型：`string`、`int`、`float`、`bool`、`choice`、`path`、`list`。
- 条件采用结构化数据，不执行字符串表达式。
- `choice.options` 是静态选项；第一阶段没有命令执行、变量插值、模板或动态选项。
- 镜像由一个基础镜像和有序 layer 组成，每个 layer 自动继承上一层结果。
- 当前 Docker Provider 使用本机 Docker CLI；不包含容器启动、Compose、多架构、推送和场景编排。

## 安装

```bash
python -m pip install -e .
```

开发环境：

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
```

## Schema v1

```yaml
version: 1

parameters:
  target:
    type: choice
    description: 运行目标
    options: [simulation, hardware]
    default: simulation

  debug:
    type: bool
    default: false

  vehicle_count:
    type: int
    default: 1
    min: 1
    max: 20

  serial_device:
    type: path
    enabled_if:
      target: hardware
    required: true

  namespace:
    type: string
    pattern: "^[a-z][a-z0-9_]*$"
    required_if:
      all:
        - target: simulation
        - not:
            debug: true

  labels:
    type: list
    item_type: string
    min: 1
```

每个参数支持以下字段：

| 字段 | 含义 |
|---|---|
| `type` | 参数类型，省略时为 `string` |
| `description` | 交互提示所用说明 |
| `default` | 内置默认值 |
| `required` | 参数启用时始终必填 |
| `enabled_if` | 条件为真时启用；禁用参数不进入结果 |
| `required_if` | 条件为真时必填 |
| `options` | `choice` 的非空静态选项 |
| `min` / `max` | 数字的闭区间，或 `list` 的长度范围 |
| `pattern` | `string` 的完整匹配正则表达式 |
| `must_exist` | `path` 是否必须在解析时存在 |
| `item_type` | `list` 元素类型；不支持嵌套 `list` |

参数名必须匹配 `^[A-Za-z][A-Za-z0-9_.-]*$`。

### 条件语法

普通 mapping 表示所有键均与已解析值相等：

```yaml
enabled_if:
  target: hardware
  debug: false
```

复杂条件仅支持 `all`、`any` 和 `not`，每个操作符 mapping 只能有一个键：

```yaml
required_if:
  any:
    - target: hardware
    - all:
        - target: simulation
        - not:
            debug: true
```

条件引用形成显式依赖 DAG。引擎会先拒绝未知引用、自引用和循环依赖，再按稳定的拓扑顺序解析。

## 取值与优先级

优先级从低到高固定为：

1. Schema 中的 `default`
2. `--values` 指定的 YAML mapping
3. 环境变量 `TOOL_PARAM_<参数名大写>`
4. 可重复的 CLI `--set NAME=VALUE`
5. 前四层都未提供必填值时，交互式输入

参数名中的点、连字符等非字母数字字符在环境变量中转换为下划线。例如 `build.type` 对应 `TOOL_PARAM_BUILD_TYPE`。若两个参数映射到同一环境变量，Schema 会被拒绝。

值在选定最高优先级来源后只转换、校验一次。`bool` 接受 `true/false`、`yes/no`、`on/off`、`1/0`；`list` 接受 YAML list、JSON list 或逗号分隔字符串。values 文件和 CLI 中出现未知参数会报错。

## 分层镜像

镜像定义与参数放在同一个 `toolchain.yaml` 中：

```yaml
version: 1

parameters:
  base_image:
    type: choice
    options: [ubuntu:22.04, ubuntu:24.04]
    default: ubuntu:22.04

  ros_distro:
    type: choice
    options: [humble, jazzy]
    default: humble

images:
  development:
    description: Robot development environment
    base:
      parameter: base_image
    context: .
    tag: example/robot-development:latest
    build_args:
      ROS_DISTRO:
        parameter: ros_distro
      DEBIAN_FRONTEND: noninteractive
    layers:
      - name: system
        dockerfile: docker/layers/10-system.Dockerfile
      - name: ros
        dockerfile: docker/layers/20-ros.Dockerfile
        build_args:
          INSTALL_EXTRAS: false
```

`base`、`tag` 和 build argument 可以是 YAML 标量，也可以通过 `{parameter: name}` 显式引用已解析参数。项目级 build arguments 会与 layer 级参数合并，同名参数以 layer 为准。

每个 layer 文件是 Dockerfile 片段，不能包含 `FROM`：

```dockerfile
ARG ROS_DISTRO
RUN echo "Installing ROS ${ROS_DISTRO}"
```

工具链会自动生成完整 Dockerfile，并把前一层构建结果作为后一层的 `FROM`。中间镜像使用确定性的内部 tag，最后一层使用配置中的最终 tag。Docker parser directive、多阶段 `FROM`、动态 layer 和 Dockerfile 模板不属于当前版本。

所有相对路径均以 `toolchain.yaml` 所在目录为基准。

## CLI

在交互式终端直接运行 `toolchain` 会打开编号菜单；菜单和子命令复用同一组应用层用例。菜单中的参数修改只在当前会话生效，不会改写配置文件。

```console
$ toolchain
Toolchain
Configuration: toolchain.yaml
1. Build image
2. Configure parameters
3. Show effective parameters
4. Validate configuration
0. Exit
Select: 1

Build image
1. development — Robot development environment
0. Back
Select: 1
Build development now? [y/N]: y
Built example/robot-development:latest (2 layer(s))
```

默认读取当前目录的 `toolchain.yaml`。也可以为菜单指定配置和 values 文件：

```bash
toolchain --config projects/robot/toolchain.yaml --values values.local.yaml
```

无子命令且 stdin 或 stdout 不是 TTY 时，程序打印帮助并以状态码 `2` 退出，避免 CI 意外等待输入。完整交互规则见 [CLI 菜单设计](docs/cli-menu.md)。原有子命令保持可组合、可脚本化：

```bash
# 校验 YAML、Schema、条件依赖和默认值
toolchain validate toolchain.yaml

# 查看参数依赖、拓扑顺序和环境变量名
toolchain inspect toolchain.yaml --format yaml

# 解析；缺少必填值时交互询问
toolchain resolve toolchain.yaml \
  --values values.yaml \
  --set target=hardware \
  --with-sources \
  --format json

# CI 中禁止交互，缺少必填值立即失败
toolchain resolve toolchain.yaml --non-interactive

# 构建 development 镜像，参数解析规则与 resolve 完全相同
toolchain image build toolchain.yaml development \
  --values values.yaml \
  --set ros_distro=humble \
  --non-interactive
```

退出码：`0` 成功，`2` 为 YAML、Schema、依赖或镜像定义错误，`3` 为参数/构建计划解析错误，`4` 为 Docker Backend 或镜像构建错误。

> 环境变量和 CLI 参数可能出现在进程列表、Shell 历史或日志中。密码、令牌等敏感数据应由后续 Provider 的专用秘密输入机制处理；Schema v1 不提供 `secret` 类型。

## Python API

```python
from toolchain import ParameterEngine, load_schema, load_values

engine = ParameterEngine(load_schema("toolchain.yaml"))
context = engine.resolve(
    values=load_values("values.yaml"),
    overrides={"debug": "true"},
    interactive=False,
)

print(context["debug"])
print(context.resolved("debug").source)
```

`ResolvedContext` 是只读 mapping，值来源通过 `resolved(name).source` 查询，未启用参数记录在 `context.disabled` 中。

## 当前实现范围

- 合法 Schema 可稳定加载；错误包含文件、行列和字段路径。
- 条件依赖拓扑排序确定，未知依赖和环被拒绝。
- 默认值、values、环境变量、CLI 的覆盖顺序可测试且固定。
- 所有七种参数类型均完成转换和约束校验。
- 交互模式补齐缺失必填值；非交互模式给出完整缺失列表。
- 解析结果不可变并保留每个值的来源。
- `validate`、`inspect`、`resolve` 可作为独立 CLI 使用。
- `image build` 在调用 Docker 前生成完整且确定的有序构建计划。
- Dockerfile 片段自动串接，最后生成用户指定的镜像 tag。
- Docker Provider 只消费构建计划，不读取 YAML 或参数来源。
- 镜像 Service 和 Planner 可使用 fake backend 完成无 Docker 单元测试。

后续工具链能力只消费 `ResolvedContext`，不直接读取 YAML、环境变量或终端输入。镜像构建遵循 `配置模型 → 参数上下文 → 构建计划 → 应用服务 → Provider/Backend`，未来容器、交叉编译、场景、编译和测试能力将复用相同结构。

更完整的模块职责、依赖方向和扩展约束见 [`docs/architecture.md`](docs/architecture.md)。
