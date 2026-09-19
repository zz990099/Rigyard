# Changelog

This file records notable user-facing changes. Once releases begin, the project will use semantic versioning and group entries under Added, Changed, Fixed, and Breaking Changes.

## Unreleased

### Added

- Structured user documentation for configuration, templates, runtime values, and core features.
- Project-local command aliases through `rigyard init --alias NAME`.
- User-defined test run and result-reporting commands through `rigyard test run` and
  `rigyard test report`.
- Constrained project-specific container tasks through `rigyard task run` and the fixed
  configuration-driven Tasks menu.

### Changed

- Reduced the README to a PyPI-friendly overview and quick start.
- Standardized all project documentation and internal comments on English.
- Renamed the project, distribution, Python package, CLI, configuration contract, workspace state,
  generated identifiers, examples, and documentation from Toolchain to Rigyard.

### Breaking changes

- The command is now `rigyard`, the default manifest is `rigyard.yaml`, and workspace state lives
  in `.rigyard/context.yaml`.
- `${TOOLCHAIN_ROOT}` is now `${RIGYARD_ROOT}`, and `TOOL_PARAM_*` overrides are now
  `RIGYARD_PARAM_*`.
- The import package and distribution name are now `rigyard`.
