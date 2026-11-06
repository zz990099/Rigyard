# README terminal recording

The README GIF records the real installed `rigyard` CLI in a pseudo-terminal. It shows the
interactive menu and Scene submenu, validates a project, and previews a scenario with `--dry-run`.
No Docker daemon, container, or tmux session is used by the recording.

## Reproduce

From the repository root, install the optional recording dependencies and run:

```bash
python -m pip install .
python -m pip install Pillow pexpect pyte
python scripts/record_demo.py
```

The recorder requires Bash and a monospace TrueType font. It defaults to `DejaVuSansMono.ttf`;
use `--font /path/to/font.ttf` to select another font, and `--output /path/to/output` to change the
output directory. It uses a disposable copy of `examples/robot-development`, omitting only the
custom branding so the built-in Rigyard logo is visible. The original example is unchanged.

The output in `docs/assets` includes:

- `terminal-demo.gif`: the rendered walkthrough, with pauses for reading and normalized typing speed.
- `terminal-demo.cast`: the captured terminal output in asciicast v2 format, using the same playback timeline.

The displayed menu and plan come from actual CLI output. The scene remains a plan preview;
the recording does not imply that containers or robot processes have started.

## README images

`rigyard-logo.svg` is the vector logo source; `rigyard-logo.png` is its raster export at twice the
logical size. The README uses absolute raw GitHub image URLs so both GitHub and the PyPI package
page can display the same PNG and GIF. New assets become available at the `main` URLs after merge;
when reviewing a PR, open its asset files from the PR branch.
