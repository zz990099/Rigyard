# 贡献指南

## 开发环境

项目要求 Python 3.10 或更高版本。推荐使用 uv：

```bash
uv sync --extra dev
```

也可以使用标准虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## 检查

提交前运行：

```bash
python -m ruff check .
python -m pytest
python -m pip install build twine
python -m build
python -m twine check dist/*
```

文档示例必须与当前 Schema 和 CLI 一致。修改配置模型、默认值或命令参数时，应同步更新 `docs/reference/configuration-schema.md`、对应功能文档和示例配置。

## 代码边界

- 配置文件由 `config` 层加载并定位错误。
- 运行时参数和模板由 `parameters` 层解析。
- images、containers、builds 和 scenarios 先生成不可变计划，再调用执行端。
- CLI 和交互菜单共享 application use case。

更完整的设计见[架构文档](docs/development/architecture.md)。
