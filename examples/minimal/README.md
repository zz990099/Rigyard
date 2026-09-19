# Minimal example

This project keeps the first run small: create one Ubuntu container, then invoke a custom task
from either the interactive menu or the CLI.

```bash
rigyard --config examples/minimal/rigyard.yaml validate
rigyard --config examples/minimal/rigyard.yaml container create development
rigyard --config examples/minimal/rigyard.yaml task run hello
```

Run `rigyard --config examples/minimal/rigyard.yaml` in a terminal to select **Tasks**, then
**Say hello**.
