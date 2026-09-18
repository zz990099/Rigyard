# 工程编译

toolchain 只在宿主机执行，工程编译统一通过 `docker exec` 进入既有容器执行。工具链不再提供
宿主机直接运行编译脚本的模式。

编译配置位于 manifest 指定的独立 source 中：

```yaml
sources:
  builds:
    - config/builds.yaml
```

source 文件根层级可用保留字段 `description` 作为菜单分组名。不同 source 可以有同名 build；
菜单先选择来源并显示 `description (路径)`，CLI 可用 `--source` 指定来源。

每个顶层键是一个命名编译入口：

```yaml
native:
  description: Native build
  container: nhybot_dev_${env:USER}_temp
  script: ${CONTAINER_TOOLCHAIN_ROOT}/scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: ${CONTAINER_WORKSPACE_ROOT}
  setup:
    - /opt/ros/humble/setup.bash
    - install/setup.bash
  user: root                    # 可选
  environment:
    BUILD_TYPE:
      default: Release
      prompt:
        mode: select
        message: Select build type
        options: [Debug, Release]
  timeout_seconds: 3600
```

字段含义：

- `container`：必填，既有容器名称或 ID；工具链不会创建、启动或拉取容器。
- `container` 也可以写成带 `source` 的 `select` prompt（见 README 运行时值一节），让菜单在
  交互时列出可用容器供选择，例如
  `prompt: {mode: select, message: …, source: {provider: docker-containers, filter: "^nhybot_dev_"}}`。
- `script`：必填，容器内脚本路径。
- `interpreter`：非空 argv，默认是 `[/bin/sh, -eu]`。
- `workdir`：可选的容器内工作目录；省略时使用容器默认工作目录。
- `user`：可选的容器内用户。
- `setup`：可选的容器内 setup 脚本列表，按顺序 source 后再执行 `script`。
- `environment`：容器内环境变量覆盖；不会继承宿主机环境。
- `timeout_seconds`：可选，范围为 1 到 86400 秒；缺省时不限制。

容器必须已经存在且正在运行。不存在或已停止时，`toolchain build` 会直接报错，不会自动处理
容器生命周期。

所有业务字段均可使用内联运行时 prompt。只有选中的 build 会进行参数求值：

```bash
toolchain build native
toolchain build native --non-interactive \
  --set builds.native.environment.BUILD_TYPE=Debug
toolchain build native --dry-run
```

`--dry-run` 完成配置校验、参数解析和计划生成，但不调用 Docker。预览会显示容器、工作目录、
完整 `docker exec` 命令、setup 和环境覆盖变量名。实际执行时容器内命令等价于：

```text
. /opt/ros/humble/setup.bash && \
. install/setup.bash && \
exec /bin/bash -euo pipefail /ros2_ws/src/nhybot/.toolchain/scripts/build-native.sh
```

`timeout_seconds` 控制宿主机上的 `docker exec` client；它不保证能可靠终止容器内已启动的
子进程。需要严格超时语义时，应在 build script 内部使用容器内的 `timeout` 工具。
