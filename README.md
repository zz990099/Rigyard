# toolchain

`toolchain` 是一个面向通用开发工具链的 YAML 声明式参数引擎。当前第一阶段只解决参数定义、依赖分析、分层取值、交互补全、类型校验和不可变结果输出；不包含 Docker、ROS、构建、测试或场景启动功能。

## 状态与边界

- Schema 只支持 YAML，版本固定为 `1`。
- 运行时要求 Python 3.10+。
- 参数类型：`string`、`int`、`float`、`bool`、`choice`、`path`、`list`。
- 条件采用结构化数据，不执行字符串表达式。
- `choice.options` 是静态选项；第一阶段没有命令执行、变量插值、模板或动态选项。

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

## CLI

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
```

退出码：`0` 成功，`2` 为 YAML、Schema 或依赖错误，`3` 为取值解析错误。

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

## 第一阶段验收范围

- 合法 Schema 可稳定加载；错误包含文件、行列和字段路径。
- 条件依赖拓扑排序确定，未知依赖和环被拒绝。
- 默认值、values、环境变量、CLI 的覆盖顺序可测试且固定。
- 所有七种参数类型均完成转换和约束校验。
- 交互模式补齐缺失必填值；非交互模式给出完整缺失列表。
- 解析结果不可变并保留每个值的来源。
- `validate`、`inspect`、`resolve` 可作为独立 CLI 使用。

后续工具链能力将只消费 `ResolvedContext`，不直接读取 YAML、环境变量或终端输入，从而保持参数系统与 Docker、ROS、构建、测试等执行后端解耦。

