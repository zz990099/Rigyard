# CLI 与交互式菜单

## 两种入口

`toolchain` 不带子命令时进入菜单；带子命令时直接执行：

```bash
toolchain
toolchain image build development
toolchain container create development
```

两条路径共用应用 use case。全局 `--config/-f` 指定 Schema v2 manifest，默认是 `./toolchain.yaml`。

## 一次性菜单

一级菜单只有镜像构建和容器创建。选择一个动作后，程序完成以下流程：

1. 选择命名配置。
2. 按需询问该配置内的运行时值。
3. 生成并展示经过验证的计划。
4. 请求最终确认。
5. 执行、取消或报告错误，然后退出进程。

菜单不会在动作结束后重新进入一级目录。操作失败会保留和对应直接 CLI 相同的退出码；`Ctrl+C` 返回 130。在二级选择页面选择 Back 也会结束当前进程。

配置管理能力只保留为直接命令：

```bash
toolchain validate
toolchain inspect --format json
toolchain resolve --non-interactive
```

## 自动化

CI 中必须明确禁止交互，并通过可选 values 文件、环境变量或完整路径覆盖提供值：

```bash
toolchain --config toolchain.yaml image build development \
  --values ci-values.yaml --non-interactive

toolchain container create development \
  --set containers.development.name=robot-ci \
  --set containers.development.privileged=false \
  --non-interactive
```

`inspect` 显示所有运行时路径、交互模式和环境变量名；`resolve` 解析全部路径并物化所有业务模型，适合作为部署前检查。

