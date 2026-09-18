# CLI 参考

## 全局入口

```text
toolchain [--version] [-f PATH] [--values PATH] [--color MODE] COMMAND
```

| 参数 | 说明 |
| --- | --- |
| `--version` | 输出版本 |
| `-f, --config PATH` | 显式指定根 manifest，覆盖工作区绑定 |
| `--values PATH` | 菜单使用的运行时 values 文件 |
| `--color auto\|always\|never` | 输出颜色，默认 `auto` |

不带 COMMAND 时进入一次性交互菜单。stdin 不是终端时输出帮助并返回 2。

## 配置命令

```bash
toolchain validate
toolchain inspect [--format json|yaml]
toolchain resolve [--values FILE] [--set PATH=VALUE] \
  [--non-interactive] [--with-sources] [--format json|yaml]
```

- `validate`：验证所有配置和模板语法。
- `inspect`：列出内联运行时参数。
- `resolve`：解析全部运行时参数；`--with-sources` 输出值来源。

## 业务命令

```bash
toolchain image build NAME [resolution options]
toolchain container create NAME [--dry-run] [resolution options]
toolchain build NAME [--dry-run] [resolution options]
toolchain scene ACTION SCENE [PROFILE] [scene options] [resolution options]
```

通用 resolution options：

| 参数 | 说明 |
| --- | --- |
| `--source PATH` | 同名定义存在时选择 source 文件 |
| `--values PATH` | 当前动作的 values YAML |
| `--set PATH=VALUE` | 覆盖参数，可重复 |
| `--non-interactive` | 禁止提示，缺少值时报错 |

当前 `image build` 会直接执行，没有 `--dry-run`。container create、build 和 scene start 支持计划预览。

scene actions：

| action | 附加参数 |
| --- | --- |
| `start` | `--instance NAME`、`--dry-run`、`--replace`、`--no-attach` |
| `stop` | `--instance NAME` |
| `down` | 无；Compose 场景专用，不接受 `--instance` |
| `status` | `--instance NAME` |
| `attach` | `--instance NAME`、`--group GROUP` |
| `logs` | `--instance NAME`、`--group GROUP`、`--follow` |

`--instance` 可重复。精确参数以 `toolchain COMMAND --help` 为准。

## 工作区初始化

```bash
toolchain init -f PATH [--force] [--alias NAME]
```

命令验证配置并在当前目录写入 `.toolchain/context.yaml`。解析顺序为显式 `--config`、当前目录绑定、当前目录 `toolchain.yaml`；不会向父目录查找。

配置位于工作区内时，绑定记录使用相对路径，以便宿主机和容器使用不同挂载根。重复绑定相同配置是幂等的，改绑需使用 `--force`。

`--alias NAME` 在工作区根目录生成可执行包装脚本：

```bash
toolchain init -f src/robot/.toolchain/toolchain.yaml --alias robot
./robot build native
```

脚本从自身目录定位绑定配置并调用稳定的 `toolchain --config ...`，不会修改 PATH 或写入用户全局 bin。已有同名文件默认不覆盖，使用 `--force` 明确替换。

## 菜单

菜单提供 Build image、Create container、Build project 和 Scene（Start/Stop/Down）。一次动作成功、失败或取消后进程退出，不循环回到首页。菜单与直接 CLI 共用相同 application use case。

计划确认默认 `[Y/n]`；删除同名容器并重建是唯一默认 `[y/N]` 的确认。

## 输出颜色

`--color=auto` 仅在输出流是终端时着色。`NO_COLOR`、`TERM=dumb` 或 `--color=never` 会禁用颜色，适合 CI 和日志重定向。
