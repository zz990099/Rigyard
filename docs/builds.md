# 工程编译

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
  script: scripts/build-native.sh
  interpreter: [/bin/bash, -euo, pipefail]
  workdir: .
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

- `script`：必填，工程维护的脚本；路径相对于根 `toolchain.yaml`。
- `interpreter`：非空 argv，默认是 `[/bin/sh, -eu]`。
- `workdir`：脚本工作目录，默认是 manifest 所在目录。
- `environment`：在继承的宿主环境上增加或覆盖的变量。
- `timeout_seconds`：可选，范围为 1 到 86400 秒；缺省时不限制。

所有业务字段均可使用内联运行时 prompt。只有选中的 build 会进行参数求值：

```bash
toolchain build native
toolchain build native --non-interactive \
  --set builds.native.environment.BUILD_TYPE=Debug
toolchain build native --dry-run
```

`--dry-run` 完成配置校验、参数解析和计划生成，但不启动脚本。预览只显示环境覆盖的变量名，不显示变量值。正常执行时不会启动隐式 shell，最终 argv 是 `interpreter + script`；需要 Bash 语义时必须在 `interpreter` 中明确指定 Bash。
