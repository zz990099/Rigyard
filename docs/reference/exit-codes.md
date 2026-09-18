# Exit codes

| Code | Meaning | Common causes |
| ---: | --- | --- |
| `0` | Success | Execution, validation, or dry-run completed |
| `1` | Unclassified Toolchain error | Generic application boundary failure |
| `2` | Configuration or usage error | YAML, schema, workspace binding, CLI arguments, or non-TTY menu use |
| `3` | Resolution or planning error | Missing runtime value, template failure, or invalid plan constraint |
| `4` | Execution backend error | Docker/tmux unavailable or image, container, build, or scenario execution failed |

External process failures are wrapped in stable Toolchain errors and written to stderr. A script, Docker, or tmux exit status is not guaranteed to become the Toolchain process exit code directly.
