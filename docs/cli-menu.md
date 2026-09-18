# CLI 与交互式菜单

## 两种入口

`toolchain` 不带子命令时进入菜单；带子命令时直接执行：

```bash
toolchain
toolchain build native
toolchain scene start robot-system development
toolchain image build development
toolchain container create development
```

两条路径共用应用 use case。全局 `--config/-f` 显式指定 Schema v3 manifest，并覆盖工作区初始化记录。

除 `scene down` 外，`scene` 子命令都接受可重复的 `--instance NAME`，只操作部分 instance；`attach/logs` 还需要
`--instance` 才能把 `--group` 定位到具体 pane：

```bash
toolchain scene start robot-system development --instance robot1
toolchain scene logs  robot-system development --instance robot1 --group navigation
toolchain scene down  robot-system development
```

`scene down` 只用于配置了 Compose 的场景，会停止 tmux 并清理完整 Compose project，因此不接受
`--instance`。

## 工作区初始化

当根配置不在日常执行命令的目录时，可以将当前目录绑定到该配置：

```bash
cd /ros2_ws
toolchain init -f src/xbot/.toolchain/toolchain.yaml
```

命令验证配置后写入当前目录的 `.toolchain/context.yaml`。后续只有从 `/ros2_ws` 本身运行
`toolchain` 才会读取该记录；不会从子目录向上搜索。配置定位优先级为：

1. 显式全局 `--config/-f`。
2. 当前目录的 `.toolchain/context.yaml`。
3. 当前目录的 `toolchain.yaml`。

初始化目标位于当前目录内部时记录相对路径，位于外部时记录绝对路径。重复初始化到同一配置
不会改写文件；切换到另一配置需要显式使用 `--force`：

```bash
toolchain init -f /opt/robot/toolchain.yaml --force
```

## 一次性菜单

一级菜单包含镜像构建、容器创建、工程编译和场景管理。`Scene…` 是二级菜单，包含启动、停止和
`down`（清理 Compose 环境）三个动作。选择一个动作后，程序完成以下流程：

1. 选择命名配置。
2. 按需询问该配置内的运行时值。
3. 生成并展示经过验证的计划。
4. 请求最终确认（默认 `[Y/n]`，直接回车即执行）。
5. 执行、取消或报告错误，然后退出进程。

唯一例外是创建容器时遇到同名容器：是否删除并重新创建默认 `[y/N]`，回车表示不删除（取消创建）。

场景选择先选来源文件、再选场景；**场景只配置了一个 profile 时直接采用它，不再询问**，多个
profile 时才出现 `Select profile`。`Stop scene` 只关闭 tmux（容器保留），`Down scene` 只对
配置了 `compose` 的场景可用，会停止 tmux 并执行 Compose down；没有 Compose 场景时该动作会
提示改用 `Stop scene` 并返回退出码 2。

如果配置包含 lifecycle hooks，计划预览会显示阶段、名称、脚本路径、脚本哈希、解释器、用户、工作目录和超时，但不会显示脚本内容或环境变量值。容器创建成功后执行 hooks，全部完成才报告整个操作成功。

菜单不会在动作结束后重新进入一级目录。操作失败会保留和对应直接 CLI 相同的退出码；`Ctrl+C` 返回 130。在二级选择页面选择 Back 也会结束当前进程。

配置管理能力只保留为直接命令：

```bash
toolchain validate
toolchain inspect --format json
toolchain resolve --non-interactive
```

## 输出样式

菜单与 CLI 共用 `src/toolchain/cli/style.py` 里按"角色"定义的配色（`DEFAULT_THEME`）：标题加粗
青、字段名暗、字段值加粗、选项序号青、次要信息（路径 / 默认值 / `Back`）暗、成功绿、警告黄、
错误加粗红。计划预览（`--dry-run`）与菜单里的计划行都用"字段名暗 + 值加粗"渲染。

计划行本身是结构化的：每个 `Line` 由若干 `(角色, 文本)` 片段组成，因此同一个业务模块可以复用
角色做细粒度区分——例如 `Mount: /a -> /b (bind, rw)` 的箭头与括号是"次要信息"、源/目标是"值"，
`Window robot: container=… -> drivers, …` 里的 `container=`、`->` 是"次要信息"。运行时提示语
（`prompt` 的消息、默认值方括号、动态候选的序号/名字/说明）走同一套角色；`str(line)` 仍是纯文本，
所以日志与测试不依赖样式。

着色只在输出流是终端时生效，可用全局 `--color=auto|always|never`（默认 `auto`）覆盖；`NO_COLOR=1`
或 `TERM=dumb` 同样关闭。因此管道、重定向与 CI 日志保持纯文本，`toolchain validate | cat` 之类的
用法不会被 ANSI 转义污染。

## 自动化

CI 中必须明确禁止交互，并通过可选 values 文件、环境变量或完整路径覆盖提供值：

```bash
toolchain --config toolchain.yaml image build development \
  --values ci-values.yaml --non-interactive

toolchain build native \
  --set builds.native.environment.BUILD_TYPE=Release \
  --non-interactive

toolchain scene start robot-system deployment --non-interactive

toolchain scene start robot-system deployment \
  --instance robot1 --non-interactive

toolchain container create development \
  --set containers.development.name=robot-ci \
  --set containers.development.privileged=false \
  --non-interactive
```

`build` 会在既有且正在运行的容器内执行，CI 中需先创建并启动目标容器。

`inspect` 显示所有运行时路径、交互模式和环境变量名；`resolve` 解析全部路径并物化所有业务模型，适合作为部署前检查。
