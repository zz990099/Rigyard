# Release process

The repository has a Release-triggered publishing workflow. Creating a GitHub Release with a tag
such as `v1.0.0` runs the tests, builds and checks a wheel and source distribution, exercises the
wheel with real Docker/Compose/tmux, and uploads those same artifacts to PyPI. Draft Releases do
not publish. The tag must point to a commit in `main` and match the package version exactly.

## One-time PyPI setup

Complete this before publishing the first GitHub Release. GitHub cannot configure a PyPI account
on your behalf.

1. Confirm that the distribution name `rigyard` can be registered on PyPI. A pending publisher
   does not reserve the name. If the project already exists, you must own it to add a publisher.
2. In [PyPI's publishing settings](https://pypi.org/manage/account/publishing/), register a
   **pending trusted publisher** (or add one to the existing project) with these exact values:

   | Field | Value |
   | --- | --- |
   | PyPI project | `rigyard` |
   | GitHub owner | `zz990099` |
   | GitHub repository | `Rigyard` |
   | Workflow filename | `publish.yml` |
   | Environment | `pypi` |

3. Set up the `pypi` GitHub Environment for this repository. Restrict deployment to release
   tags if you use environment deployment rules. Required reviewers are optional: enabling them
   pauses publishing until a reviewer approves the job.

The publishing job uses GitHub OIDC with `id-token: write`; it needs no long-lived PyPI API
token. The account configuration above must match the workflow and environment names precisely.
The first successful upload converts the pending publisher into a normal publisher.

## Prepare a version

1. Check that the configuration schema, CLI commands, workspace state, and upgrade behavior are
   ready to support as public interfaces. Run real project workflows in a Linux Docker environment.
2. Update `src/rigyard/version.py`, `CHANGELOG.md`, and the development-status classifier in
   `pyproject.toml`. Hatch reads the version from `version.py`. Choose a new version: PyPI will
   not replace existing distribution files with the same name.
3. Review package description, URLs, README links, license, installation instructions, and
   `requires-python`. Do not present the checkout bootstrap script as a file installed by PyPI.
4. Merge the changes into `main` and wait for CI to pass. CI tests Python 3.10–3.13, validates
   metadata, installs both wheel and sdist into separate clean environments, and exercises
   Docker, Compose, and tmux with a wheel installed from the built artifact.

## Local checks

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src/rigyard
pyright src/rigyard
pytest --cov=rigyard --cov-report=term-missing --cov-fail-under=90
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
python scripts/verify_distributions.py dist
```

The Docker smoke test requires an accessible daemon, Docker Compose v2, tmux, and an installed
`rigyard` command:

```bash
bash tests/integration/smoke.sh
```

The script creates temporary project files, a disposable image/container and Compose project,
then removes them on exit. Run it on a disposable host if your Docker daemon is remote.

## Publish

Create a GitHub Release from a tag `vX.Y.Z` (or `X.Y.Z`) on the tested `main` commit.
Publishing the Release triggers [`publish.yml`](../../.github/workflows/publish.yml).
Its PyPI job runs only after tests, artifact validation, and the Docker smoke test succeed.
The workflow builds once and downloads the same artifacts in the isolated publishing job.
Check the workflow result and the files on PyPI, then install the released version into a clean
environment and run `rigyard --version`.

TestPyPI is a separate index and account. If you use it for a practice upload, configure its
Trusted Publisher separately and perform that upload before creating the production Release.
This production workflow does not publish to TestPyPI.
