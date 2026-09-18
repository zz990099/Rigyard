# Contributing

## Development environment

The project requires Python 3.10 or newer. The recommended setup uses uv:

```bash
uv sync --extra dev
```

Alternatively, use a standard virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Checks

Run these checks before submitting a change:

```bash
python -m ruff check .
python -m pytest
python -m pip install build twine
python -m build
python -m twine check dist/*
```

Documentation examples must match the current schema and CLI. When changing configuration models, defaults, or command arguments, update `docs/reference/configuration-schema.md`, the relevant feature guide, and the example configuration.

## Code boundaries

- `config` loads manifest and source files and reports source locations.
- `parameters` resolves runtime values and string templates.
- `images`, `containers`, `builds`, and `scenarios` create immutable plans before invoking an executor.
- The CLI and interactive menu share application use cases.

See the [architecture guide](docs/development/architecture.md) for more detail.
