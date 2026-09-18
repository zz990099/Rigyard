# Images

The image feature builds ordered Dockerfile fragments as a layered image. Each layer uses the previous output as its base, and the final layer receives the configured final tag.

## Minimal configuration

Root manifest:

```yaml
sources:
  images: config/images.yaml
```

`config/images.yaml`:

```yaml
development:
  base: ubuntu:22.04
  tag: example/robot-development:latest
  layers:
    - name: system
      dockerfile: docker/layers/10-system.Dockerfile
    - name: application
      dockerfile: docker/layers/20-application.Dockerfile
```

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | ---: | --- | --- |
| `description` | string | no | — | Menu description |
| `base` | string | yes | — | Base image for the first layer; tag or digest |
| `context` | path | no | `.` | Docker build context |
| `tag` | string | yes | — | Final image tag; digests are not allowed |
| `tag_alias` | string | no | — | Stable tag updated after all layers succeed |
| `build_args` | scalar mapping | no | `{}` | Build arguments applied to every layer |
| `layers` | list | yes | — | At least one uniquely named layer |
| `layers[].name` | string | yes | — | Layer name |
| `layers[].dockerfile` | path | yes | — | Dockerfile fragment |
| `layers[].build_args` | scalar mapping | no | `{}` | Build arguments added or overridden for this layer |

Except for `description` and layer names, business values accept corresponding [runtime values](../configuration/runtime-values.md). Strings and paths support [templates](../configuration/templates.md). Build argument names must match `[A-Za-z_][A-Za-z0-9_]*`; values may be strings, integers, floats, or booleans.

## Build rules

Dockerfile fragments cannot contain:

- A `FROM` instruction
- A `# syntax=...` or `# escape=...` parser directive
- Empty content

Rigyard creates a complete Dockerfile for every layer, using the previous result as `FROM`. Root and layer build arguments are merged, with layer values winning on duplicate keys. Boolean arguments become lowercase `true` or `false`.

Relative `context` and `dockerfile` paths are based on the root manifest directory. The context must be an existing directory, and fragments must be readable UTF-8 files.

## Intermediate tags and aliases

Intermediate layers use stable local tags derived from the root manifest path, image name, layer index, and layer name. Only the final layer uses `tag`.

```yaml
development:
  base: ubuntu:22.04
  tag: example/development:${date:%Y%m%d}
  tag_alias: example/development:latest
  layers:
    - name: system
      dockerfile: docker/system.Dockerfile
```

After every layer succeeds, Rigyard performs the equivalent of:

```bash
docker tag example/development:20260918 example/development:latest
```

A failed build does not update the alias. If alias tagging fails, the original final tag remains. No extra tag command runs when `tag_alias` equals `tag`.

## Commands

```bash
rigyard image build development
rigyard image build development --source config/images.yaml
rigyard image build development --non-interactive \
  --set images.development.base=ubuntu:24.04
```

`image build` currently has no `--dry-run` and invokes Docker after planning. Use `rigyard validate` for schema and template syntax and `rigyard resolve --non-interactive` for parameter checks. Dockerfile content and the context are checked during the actual build's planning phase.
