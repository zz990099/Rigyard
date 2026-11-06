# Scenario autostart (systemd)

Autostart registers an existing scenario/profile to start at boot without a login or terminal.
No changes to scenario YAML and no `boot` profile are required. Profile names remain arbitrary.
Both existing-container and Compose scenarios use the existing tmux execution path.

## Menu and CLI

Select **Scene → Autostart… → Enable / Disable / Status**, then use the same source-directory,
file, scene and profile selection as Start scene. Enable asks the existing runtime prompts,
including container selection; Disable and Status do not ask them again.

```bash
rigyard scene autostart enable robot development
rigyard scene autostart enable robot development --non-interactive \
  --set scenarios.robot.instances.robot1.container=robot-dev
rigyard scene autostart enable robot development --dry-run
rigyard scene autostart status robot development
rigyard scene autostart disable robot development
```

Enable installs/enables the service for the next boot; it does not interrupt a manual run.
Disable cancels future boot startup but leaves a running scene alone. CLI `--now` explicitly
starts/stops immediately. Menu operations use the non-immediate defaults.
Repeated Enable updates the same service. Stop an active service before updating its registration.
Use `--source` when scene names are ambiguous. The unit name printed by Enable is stable for
config path + source path + scene + profile; moving the project requires a new registration.

When YAML has been deleted, the printed unit name still works:

```bash
rigyard scene autostart status --unit rigyard-autostart-<64-character-key>.service
rigyard scene autostart disable --unit rigyard-autostart-<64-character-key>.service --now
```

## What is installed

One Rigyard-marked file under `/etc/systemd/system/`. The unit calls the absolute Python
interpreter used by Rigyard, with `-m rigyard`, an absolute config/source path and explicit
workspace root. Keep that interpreter, Rigyard installation, and project available at boot. The generated
`_start` / `_stop` subcommands are internal lifecycle adapters, not new scene definitions.

The service runs as the user who enabled it. Only installation and systemctl mutations use sudo.
The first version supports Linux systemd and the local system Docker daemon; remote/rootless
Docker is rejected. Enable checks Docker access and existing container targets before installing.
It does not build images, create missing existing containers, or start a scene unless `--now` is used.

Prompt answers are typed CLI arguments in the unit, before input-template/append processing.
No parameter snapshot YAML/JSON is created. Ordinary scripts/commands are still loaded from
current scenario YAML at each start; date templates are evaluated at start. Change a saved
choice by running Enable again. Changes that remove a prompt or make a saved answer invalid
fail explicitly; regenerate the registration. New required prompts never block waiting for input.

The unit captures HOME/USER/LOGNAME, PATH, Docker connection settings and referenced environment
variables. It does not source interactive shell startup files or copy the entire environment.
Compose interpolation should be defined in its `.env` file or `scenario.compose.environment`;
implicit arbitrary shell variables are not captured. GUI/session-dependent scenes need their
own explicitly configured runtime environment. Unit files and process arguments are not secret
storage: do not use runtime prompt answers to carry credentials.

Existing `.rigyard/runs` control records are retained. They store runtime targets, unit ownership,
tmux socket and boot identity, not executable node scripts. Old records remain readable.

## Lifecycle and status

By default the scene uses the enabling user's standard tmux socket. As the same user, run
`tmux ls` and `tmux attach -t <session>` from a shell with the standard tmux environment.
Choose **Use an isolated tmux socket? → Yes** or pass `--isolated-socket` to Enable for a
dedicated server. Previously generated units also use the default socket on their next start.
To change the selection, stop the service and enable the same scene/profile again.
A manual Start cannot replace a currently recorded systemd-owned scene, or vice versa; stop the
current owner first. Stop scene routes systemd-owned runs through systemctl, while preserving
the enabled/disabled setting. Same-project recorded container conflicts involving autostart
are rejected, as are existing Compose-project conflicts. This is not a machine-wide resource
scheduler: separately configured projects must not share containers or Compose project names.

The unit uses `Type=oneshot` with `RemainAfterExit=yes`. Status reports the systemd state,
recorded scene state, tmux panes and container state separately. An active unit means its launch
completed; it does not assert application health. There is no continuous watchdog or automatic
restart policy. Existing `keep_alive`, container restart policy and startup ordering are preserved.

`ExecStop` reuses recorded complete-scene cleanup: interrupt panes, stop existing containers or
Compose down, then close tmux. `ExecStopPost` also attempts this cleanup after a failed launch.
Failed cleanup retains its control record for diagnosis/retry; it never cleans a later manual run.
Service launch/cleanup errors are in `journalctl -u <unit>`; node output remains in scene logs/tmux.

## Verification

Unit tests cover typed answer replay, escaping, ownership, previous-boot records, CLI/menu
behavior, registration rollback and isolated tmux commands. The Docker smoke CI also runs
`tests/integration/autostart.sh` against real systemd, Docker and tmux, including failure cleanup,
missing source YAML and both container modes. A physical reboot/power-cycle remains a target-host
acceptance check; the hosted CI does not reboot its runner.
