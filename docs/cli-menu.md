# Interactive CLI menu

The command CLI and the interactive menu are two presentation adapters over the same application use cases. Neither adapter calls the other, constructs a fake `argparse.Namespace`, or owns build and parameter-resolution rules.

## Ownership rules

| Concern | Owner |
|---|---|
| Available toolchain capabilities and action handlers | Code registry |
| Images, parameters, descriptions, and choices | `toolchain.yaml` |
| Values file and environment inputs | Parameter subsystem |
| Temporary choices made while the menu is open | `MenuSession` |
| Image building behavior | `BuildImageUseCase` and image service |

Schema v1 does not have a `menu` or `ui` section. Project configuration cannot name Python handlers or arbitrary shell commands. Future project-defined workflows must be modeled as a workflow domain rather than as menu entries.

## Entry behavior

- A normal subcommand continues to use the command CLI.
- No subcommand starts the menu only when both stdin and stdout are TTYs.
- A non-TTY invocation with no subcommand prints help and exits with status 2.
- The menu reads `./toolchain.yaml` by default. `--config` selects another file.
- `--values` supplies an optional values file for the menu session.

## Initial actions

The first menu contains only implemented capabilities:

1. Build image
2. Configure parameters
3. Show effective parameters
4. Validate configuration
0. Exit

The action registry is explicit and static. `Build image` is unavailable when the loaded configuration has no images. Its image submenu is generated from `ToolchainConfig.images`.

## Session overrides

Parameter edits are held in memory and passed to the same parameter resolver as CLI `--set` values. They are not written to YAML. The effective precedence remains:

```text
default < values file < environment < session override
```

Changing a dependency can enable or disable other parameters. The parameter screen therefore creates a fresh partial resolution every time it is rendered. A normal build still requires a complete resolution and prompts for missing required values.

## Interaction rules

- Invalid menu input is reported and retried.
- `Ctrl+C` during an action cancels it and returns to the main menu.
- `Ctrl+C` at the main selection exits with status 130.
- EOF exits cleanly.
- An image build requires confirmation.
- An action error is displayed without discarding session overrides.
- Successful and failed actions return to the main menu.

This is deliberately a numbered prompt, not a full-screen TUI. It uses no additional UI dependency.

