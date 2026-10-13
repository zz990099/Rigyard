# Changelog

This file records notable user-facing changes. Releases use semantic versioning and group entries under Added, Changed, Fixed, and Breaking Changes.

## Unreleased

## 1.0.4 - 2026-10-13

### Fixed

- Replace `--provenance=false` with `BUILDX_NO_DEFAULT_ATTESTATIONS=1` in the Docker build
  subprocess environment, avoiding unknown-option errors with older Docker build frontends
  while disabling default provenance attestations on supported Buildx versions.
- Preserve inherited Docker connection settings, proxy settings, and other environment
  variables without changing the host environment. No Rigyard configuration changes are required.

## 1.0.3 - 2026-10-11

### Fixed

- Explicitly disable provenance attestations for every image layer, including the final image,
  to prevent build-specific metadata from changing image index digests for unchanged contents.
  Docker must support `--provenance=false`; no Rigyard configuration changes are required.
- Update the package version to match the new release. The `1.0.2` GitHub Release did not
  publish to PyPI because its artifacts still declared version `1.0.1`. This release includes
  the image-build fix from that attempt.

### Changed

- Document checking distribution versions against the intended release tag before publishing.

## 1.0.1 - 2026-09-28

### Added

- A standalone Linux `bootstrap_from_pypi.sh` that installs Rigyard from PyPI with uv-managed
  Python, without a repository checkout, preinstalled Python, or shell activation.
- Optional `--version` selection for the PyPI bootstrap.

### Changed

- Installation guidance now starts with the no-checkout PyPI setup and direct executable use.

### Fixed

- PyPI bootstrap replaces a same-version installation made from a local checkout.
- Bootstrap fails if the installed Rigyard executable cannot start.

## 1.0.0 - 2026-09-25

### Added

- A Bash bootstrap script that installs uv and a managed Python environment, plus a script to activate it in new shells.
- A GitHub Release workflow that verifies distributions and publishes to PyPI through trusted publishing.
- Source-qualified definition catalog and `inspect/resolve --source` for ambiguous resources.
- Private, atomic scenario run records for controlling the original runtime after configuration changes.
- Injectable scenario runtime ports and separate startup/control plan models.

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

- Workspace command aliases discover the closest workspace in the current or parent directories at execution time.
- Configuration models and request overrides now freeze nested collections; serialization returns ordinary values.
- Build, test, and task use cases invoke their backends directly instead of forwarding through empty services.

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

### Fixed

- Interrupting build, test, and task commands stops their processes inside the container.
- Workspace configuration resolution follows the nearest manifest instead of retaining stale initialization state.
- Explicit overrides for prompts in a selected secondary source with a duplicate resource name.
- Scenario instance selection no longer resolves prompts belonging to unselected or disabled instances.
- `scene status --instance` now restricts the queried windows.
- String boolean enable values are validated instead of interpreted by Python truthiness.


### Breaking changes

- Generated scenario runtime names now include both the source file and profile, using the same identity for tmux and Compose. Stop/remove legacy runtime resources with the previous version before upgrading.
- Project-wide parameter inspection/resolution now rejects duplicate names unless `--source` selects a source.
- Internal build/test/task forwarding service modules have been removed; use application use cases or backend protocols.

- The command is now `rigyard`, the default manifest is `rigyard.yaml`, and workspace state lives
  in `.rigyard/context.yaml`.
- `${TOOLCHAIN_ROOT}` is now `${RIGYARD_ROOT}`, and `TOOL_PARAM_*` overrides are now
  `RIGYARD_PARAM_*`.
- The import package and distribution name are now `rigyard`.
- Removed compatibility fallbacks for assembled configurations without source provenance,
  schema version 2 migration guidance, and the old Docker runner import path.
- Removed the ineffective scenario `replace` profile field and `--replace` CLI option;
  scenario starts always replace matching tmux state.
