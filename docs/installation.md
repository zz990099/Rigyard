# 安装与系统要求

## Python

Toolchain 要求 Python 3.10 或更高版本。

项目发布到 PyPI 后，推荐用隔离的工具环境安装 CLI：

```bash
pipx install robot-toolchain
# 或
uv tool install robot-toolchain
```

也可以安装到已经激活的虚拟环境：

```bash
python -m pip install robot-toolchain
```

当前从源码安装稳定版本：

```bash
git clone https://github.com/zz990099/toolchain.git
cd toolchain
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

安装后确认命令可用：

```bash
toolchain --version
```

可编辑安装、测试和代码检查属于开发流程，见[贡献指南](../CONTRIBUTING.md)。

## 外部工具

Python 包不会安装以下系统工具：

| 功能 | 宿主机要求 | 容器要求 |
| --- | --- | --- |
| 镜像、容器、编译 | Docker CLI 和可访问的 Docker daemon | 编译脚本所需工具 |
| Compose 场景 | Docker Compose v2，即 `docker compose` | 场景命令所需工具 |
| tmux 场景 | tmux、Docker CLI | 可用的交互 shell |

Toolchain 当前面向能够运行 Docker 与 tmux 的开发环境。执行前可分别运行 `docker version`、`docker compose version` 和 `tmux -V` 检查依赖。
