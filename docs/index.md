# Toolchain 文档

Toolchain 将机器人软件开发中的镜像、容器、工程编译和多进程调试场景组织为可版本控制的 YAML 配置。工具运行在宿主机，通过 Docker 和 tmux 执行计划，不理解 colcon、CMake 或 ROS launch 等具体工程系统。

## 开始使用

- [安装与系统要求](installation.md)
- [入门教程](getting-started.md)
- [CLI 参考](reference/cli.md)
- [退出码](reference/exit-codes.md)

## 配置

- [配置总览](configuration/index.md)
- [根 manifest](configuration/manifest.md)
- [全局变量与字符串模板](configuration/templates.md)
- [运行时参数](configuration/runtime-values.md)
- [配置字段参考](reference/configuration-schema.md)

## 核心功能

- [镜像](features/images.md)
- [容器](features/containers.md)
- [工程编译](features/builds.md)
- [场景启动](features/scenarios.md)

## 项目维护

- [架构](development/architecture.md)
- [发布流程](development/releasing.md)
- [贡献指南](../CONTRIBUTING.md)
- [变更记录](../CHANGELOG.md)
