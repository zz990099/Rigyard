# 镜像

镜像功能把多个不含 `FROM` 的 Dockerfile 片段按顺序构建为分层镜像。每一层以上一层输出为基础，最后一层使用配置的最终 tag。

## 最小配置

根 manifest：

```yaml
sources:
  images: config/images.yaml
```

`config/images.yaml`：

```yaml
development:
  base: ubuntu:22.04
  tag: example/robot-development:latest
  layers:
    - name: system
      dockerfile: docker/layers/10-system.Dockerfile
    - name: application
      dockerfile: docker/layers/20-application.Dockerfile
```

## 字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | ---: | --- | --- |
| `description` | string | 否 | — | 菜单说明 |
| `base` | string | 是 | — | 第一层基础镜像，可使用 tag 或 digest |
| `context` | path | 否 | `.` | Docker build context |
| `tag` | string | 是 | — | 最终镜像 tag；不能使用 digest |
| `tag_alias` | string | 否 | — | 全部层成功后更新的固定 tag |
| `build_args` | scalar mapping | 否 | `{}` | 应用于所有层的 build args |
| `layers` | list | 是 | — | 至少一个 layer，名称必须唯一 |
| `layers[].name` | string | 是 | — | layer 名称 |
| `layers[].dockerfile` | path | 是 | — | Dockerfile 片段 |
| `layers[].build_args` | scalar mapping | 否 | `{}` | 当前层覆盖/追加的 build args |

除 `description` 和 layer `name` 外，业务值均支持其对应类型的[运行时参数](../configuration/runtime-values.md)；字符串和路径支持[模板](../configuration/templates.md)。build arg 名必须匹配 `[A-Za-z_][A-Za-z0-9_]*`，值可以是 string、integer、float 或 boolean。

## 构建规则

Dockerfile 文件是片段，不能包含：

- `FROM` 指令
- `# syntax=...` 或 `# escape=...` parser directive
- 空内容

Toolchain 为每一层动态生成完整 Dockerfile，将上一层作为 `FROM`。根级 `build_args` 与 layer 级 `build_args` 合并，同名值以 layer 为准。boolean build arg 转换为小写 `true`/`false`。

`context` 和每个 `dockerfile` 的相对路径均以根 `toolchain.yaml` 所在目录为基准。context 必须是已有目录，Dockerfile 必须是可读取的 UTF-8 文件。

## 中间层和固定别名

中间层使用基于根配置绝对路径、镜像名、序号和 layer 名生成的稳定本地 tag。只有最后一层使用 `tag`。

```yaml
development:
  base: ubuntu:22.04
  tag: example/development:${date:%Y%m%d}
  tag_alias: example/development:latest
  layers:
    - name: system
      dockerfile: docker/system.Dockerfile
```

全部层构建成功后执行等价于：

```bash
docker tag example/development:20260918 example/development:latest
```

构建失败时不会更新 alias；alias 更新失败时原始最终 tag 保留。`tag_alias` 与 `tag` 相同时不重复标记。

## 命令

```bash
toolchain image build development
toolchain image build development --source config/images.yaml
toolchain image build development --non-interactive \
  --set images.development.base=ubuntu:24.04
```

`image build` 当前没有 `--dry-run`，会在计划成功后直接调用 Docker。可先运行 `toolchain validate` 检查 Schema 和模板语法，再用 `toolchain resolve --non-interactive` 检查参数来源；Dockerfile 内容和 context 在实际 build 的计划阶段检查。
