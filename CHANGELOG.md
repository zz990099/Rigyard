# Changelog

This file records notable user-facing changes. Once releases begin, the project will use semantic versioning and group entries under Added, Changed, Fixed, and Breaking Changes.

## Unreleased

### Added

- Structured user documentation for configuration, templates, runtime values, and core features.
- Python-environment command aliases through `rigyard init --alias NAME`.
- User-defined test run and result-reporting commands through `rigyard test run` and
  `rigyard test report`.
- Constrained project-specific container tasks through `rigyard task run` and the fixed
  configuration-driven Tasks menu.
- Manifest-configured workspace command aliases with CLI override and opt-out controls.
- Terminal logos loaded from external UTF-8 files through templated paths.
- Safe, project-aware alias removal through `rigyard alias remove`.
- Prompt-local `${INPUT}` composition and explicit list append semantics for runtime values.
- Image build network modes, per-layer overrides, and an atomic interactive host-proxy group.
- Source-aware `${SOURCE_DIR}` and `${SOURCE_FILE}` templates, plus `${RIGYARD_FILE}` for the
  absolute root manifest path.

### Changed

- Generated tmux sessions, Compose projects, and pane metadata now use the `rigyard` prefix.
- CI now covers Python 3.10 through 3.13, enforces test coverage, and validates built wheel and
  source-distribution artifacts.
- Package metadata now reads its version exclusively from `src/rigyard/version.py`.
- Complete Compose scene starts now remove the previous project containers and orphans before
  recreating them; partial instance starts remain incremental.
- Build, test, and custom-task commands now start stopped target containers by default, with
  `start_container: false` available for strict lifecycle ownership.
- Reduced the README to a PyPI-friendly overview and quick start.
- Split repository examples into a minimal introduction and a full robot-development reference.
- Standardized all project documentation and internal comments on English.
- Renamed the project, distribution, Python package, CLI, configuration contract, workspace state,
  generated identifiers, examples, and documentation from Toolchain to Rigyard.

### Breaking changes

- The command is now `rigyard`, the default manifest is `rigyard.yaml`, and workspace state lives
  in `.rigyard/context.yaml`.
- `${TOOLCHAIN_ROOT}` is now `${RIGYARD_ROOT}`, and `TOOL_PARAM_*` overrides are now
  `RIGYARD_PARAM_*`.
- The import package and distribution name are now `rigyard`.
- Removed compatibility fallbacks for assembled configurations without source provenance,
  schema version 2 migration guidance, and the old Docker runner import path.
- Removed the ineffective scenario `replace` profile field and `--replace` CLI option;
  scenario starts always replace matching tmux state.
