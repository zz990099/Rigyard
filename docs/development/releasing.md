# Release process

This process is intended for future PyPI wheel and source distribution releases. Choose the final distribution name before the first upload because renaming a published PyPI project is not a normal in-place operation.

## Release preparation

1. Update `src/rigyard/version.py` and `CHANGELOG.md`. Hatch reads the package version from this single source.
2. Verify description, license, classifiers, and project URLs in `pyproject.toml`.
3. Verify that README links are publicly reachable from PyPI.
4. Run the test suite with coverage on every supported Python version.

## Local checks

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=rigyard --cov-report=term-missing --cov-fail-under=90
python -m build
python -m twine check dist/*
```

Install the artifact into a clean environment and smoke-test the CLI:

```bash
python -m pip install dist/*.whl
rigyard --version
rigyard --help
```

Inspect wheel and sdist contents to ensure they include the Python package, README, and LICENSE and exclude caches, local configuration, and credentials.

## TestPyPI

Publish the same artifacts to TestPyPI before the production release, then install and verify them from TestPyPI. TestPyPI and PyPI use separate accounts and project namespaces.

## Automated publishing

Use GitHub Actions with PyPI Trusted Publishing:

1. Trigger a dedicated build job from a tag or release.
2. Build wheel and sdist artifacts only in that job.
3. Download the existing artifacts in the publishing job; do not rebuild them there.
4. Publish through a protected GitHub Environment and OIDC.
5. Require manual approval for the PyPI environment.

Do not store long-lived PyPI API tokens in the repository. Trusted Publishing exchanges the CI identity for a short-lived, project-scoped credential.
