# Configuration schema reference

This page is a compact index for schema version 3. The feature guides define complete behavior, examples, and failure semantics. Every model rejects unknown fields.

## Common runtime types

| Type | Fixed form | Runtime form |
| --- | --- | --- |
| RuntimeText | string | PromptValue |
| RuntimePath | path string | PromptValue |
| RuntimeBool | boolean | PromptValue |
| RuntimeInteger | integer | PromptValue |
| RuntimeList | string list | PromptValue |
| RuntimeScalar | string, integer, float, or boolean | PromptValue |

A PromptValue contains an optional `default` and a required `prompt`. Prompt fields are `mode`, `message`, `options`, `source`, `repeat`, `item_hint`, `merge`, and `input_template`. Input prompts default to `merge: replace`; `merge: append` requires a list-valued PromptValue `base`. `input_template` must contain `${INPUT}` exactly once. See [Runtime values](../configuration/runtime-values.md).

## Root manifest

| Path | Type | Default |
| --- | --- | --- |
| `version` | integer; must be 3 | required |
| `metadata.name` | string | required |
| `metadata.description` | string/null | `null` |
| `workspace.command_alias` | string/null | `null` |
| `branding.logo` | UTF-8 multiline string/null | built-in Rigyard logo |
| `branding.logo_file` | path/null | built-in Rigyard logo |
| `variables` | string mapping | `{}` |
| `sources.images` | path, path list, or null | `null` |
| `sources.containers` | path, path list, or null | `null` |
| `sources.builds` | path, path list, or null | `null` |
| `sources.tests` | path, path list, or null | `null` |
| `sources.tasks` | path, path list, or null | `null` |
| `sources.scenarios` | path, path list, or null | `null` |

At least one source kind is required. See the [root manifest guide](../configuration/manifest.md).
`branding.logo` and `branding.logo_file` are mutually exclusive.

## Image source

```text
<image>.description
<image>.base
<image>.context = .
<image>.tag
<image>.tag_alias
<image>.build_args
<image>.layers[].name
<image>.layers[].dockerfile
<image>.layers[].build_args
```

`base`, `tag`, and at least one layer are required. See [Image fields](../features/images.md#fields).

## Container source

```text
<container>.description
<container>.image
<container>.name
<container>.interactive = true
<container>.tty = true
<container>.detach = true
<container>.privileged = false
<container>.devices = []
<container>.group_add = []
<container>.mounts = []
<container>.network
<container>.ipc
<container>.workdir
<container>.environment = {}
<container>.lifecycle.post_create = []
<container>.lifecycle.post_start = []
<container>.command = []
```

Hook fields are `name`, `script`, `interpreter`, `user`, `workdir`, `environment`, and `timeout_seconds`. See [Container fields](../features/containers.md#fields).

## Build source

```text
<build>.description
<build>.container
<build>.start_container = true
<build>.script
<build>.interpreter = [/bin/sh, -eu]
<build>.workdir
<build>.user
<build>.setup = []
<build>.environment = {}
<build>.timeout_seconds
```

`container` and `script` are required. See [Build fields](../features/builds.md#fields).

## Test source

```text
<test>.description
<test>.container
<test>.start_container = true
<test>.workdir
<test>.user
<test>.setup = []
<test>.environment = {}
<test>.run.script
<test>.run.interpreter = [/bin/sh, -eu]
<test>.run.timeout_seconds
<test>.report.script
<test>.report.interpreter = [/bin/sh, -eu]
<test>.report.timeout_seconds
```

`container`, `run`, and `report` are required. Each action requires `script`. See [Test fields](../features/tests.md#fields).

## Custom task source

```text
<task>.description
<task>.container
<task>.start_container = true
<task>.script
<task>.interpreter = [/bin/sh, -eu]
<task>.workdir
<task>.user
<task>.setup = []
<task>.environment = {}
<task>.timeout_seconds
<task>.menu.enabled = true
<task>.menu.label
<task>.menu.confirm = true
```

`container` and `script` are required. The optional `menu` mapping exposes the task under the fixed Tasks menu. See [Custom task fields](../features/tasks.md#fields).

## Scenario source

```text
<scenario>.description
<scenario>.compose
<scenario>.instances
<scenario>.profiles
```

Compose fields:

```text
file
project_name
wait_timeout_seconds = 60
environment = {}
```

Instance fields:

```text
description
enabled = true
container | service
groups
```

Group fields:

```text
description
enabled = true
script | command
setup = []
interpreter = [/bin/sh, -eu]
user
workdir
environment = {}
```

Profile fields:

```text
session
attach = true
stop_grace_seconds = 5
restart_container = always
mouse = true
keep_alive = true
```

See the complete [scenario configuration](../features/scenarios.md).

## Reserved source field

Every source may contain this top-level field:

```yaml
description: Human-readable source group
```

It is not a business resource and does not participate in name conflicts. Every other top-level key is a named definition for that source kind.
