# 发布流程

本流程用于未来发布 PyPI wheel 和 source distribution。首次发布前应确定最终 distribution name；PyPI 项目发布后不适合直接改名。

## 发布前准备

1. 更新版本号和 `CHANGELOG.md`。
2. 确认 `pyproject.toml` 的 description、license、classifiers 和 project URLs。
3. 确认 README 中的公开链接可从 PyPI 访问。
4. 在受支持的 Python 版本上运行测试。

## 本地检查

```bash
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest
python -m build
python -m twine check dist/*
```

还应从构建产物安装到全新虚拟环境并检查：

```bash
python -m pip install dist/*.whl
toolchain --version
toolchain --help
```

检查 wheel/sdist 内容，确保 Python 包、README 和 LICENSE 已包含，且没有测试缓存、本地配置或凭据。

## TestPyPI

正式发布前先将相同构建产物发布到 TestPyPI，并从 TestPyPI 安装验证。TestPyPI 与 PyPI 使用独立账户和项目空间。

## 自动发布

推荐 GitHub Actions 使用 PyPI Trusted Publishing：

1. tag/release 触发独立 build job。
2. build job 只生成并上传 wheel/sdist artifact。
3. publish job 下载已经生成的 artifact，不重新构建。
4. 通过受保护的 GitHub Environment 和 OIDC 发布。
5. PyPI environment 要求人工批准。

不要在仓库中保存长期 PyPI API token。首次配置 Trusted Publisher 后，使用短期项目级凭据完成上传。
