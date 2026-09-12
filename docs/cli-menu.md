# CLI 与交互式菜单

## 两种入口

`toolchain` 不带子命令时进入菜单；带子命令时直接运行同一个应用 use case：

```bash
toolchain
toolchain image build development
toolchain container create development
```

全局 `--config/-f` 设置项目配置，默认是 `./toolchain.yaml`。菜单可用全局 `--values` 初始化值；直接子命令的 `--values`、`--set` 和 `--non-interactive` 属于具体操作。

## 菜单流程

菜单提供镜像构建、运行时值配置/查看、配置校验和容器创建。选择镜像或容器后才会询问该配置子树的内联 prompts。完成取值和严格校验后展示计划，再进行最终确认；取消不会调用 Docker。

“Configure parameters”保存的是当前菜单会话中的路径覆盖值，不修改 YAML。它的优先级等同 CLI `--set`，退出菜单后丢弃。

## 自动化

CI 中应明确禁用交互：

```bash
toolchain --config toolchain.yaml image build development \
  --values ci-values.yaml --non-interactive
```

完整路径覆盖适合少量临时变更：

```bash
toolchain container create development \
  --set containers.development.name=robot-ci \
  --set containers.development.privileged=false \
  --non-interactive
```

`inspect` 显示运行时路径、交互模式、默认值状态和对应环境变量名；`resolve` 解析全部路径并物化所有业务模型，因此可用作部署前检查。

