#!/usr/bin/env bash
# Called by smoke.sh after preparing its private project and image.
set -Eeuo pipefail
project="$1"
rigyard_bin="$2"
units=()
cleanup_autostart() {
    status=$?
    trap - EXIT
    for unit in "${units[@]}"; do
        sudo systemctl disable --now "$unit" || true
        sudo rm -f -- "/etc/systemd/system/$unit"
    done
    sudo systemctl daemon-reload
    exit "$status"
}
trap cleanup_autostart EXIT

# Only modify the disposable integration fixture.
sed -i 's/restart_container: never/restart_container: always/; s/sleep 30/sleep 300/g' \
    "$project/config/scenarios.yaml"
cd -- "$project"
for scene in existing compose; do
    unit_text="$("$rigyard_bin" scene autostart enable "$scene" ci --non-interactive --dry-run)"
    unit="$(printf '%s\n' "$unit_text" | head -n1 | python -c \
        'import json,sys; print(json.loads(sys.stdin.read().split("v1 ",1)[1])["unit"])')"
    units+=("$unit")
    "$rigyard_bin" scene autostart enable "$scene" ci --non-interactive
    systemctl is-enabled "$unit"
    ! systemctl is-active --quiet "$unit"
    # Launch by systemd with no terminal or activated shell environment.
    sudo systemctl start "$unit" || { sudo journalctl -u "$unit" --no-pager; exit 1; }
    "$rigyard_bin" scene autostart status "$scene" ci
    "$rigyard_bin" scene status "$scene" ci --non-interactive
    "$rigyard_bin" scene logs "$scene" ci --instance app --group main | grep -q ready
    if "$rigyard_bin" scene start "$scene" ci --non-interactive --no-attach; then
        printf 'A manual start replaced a systemd-owned scene.\n' >&2
        exit 1
    fi
    # Disable leaves the current scene alive; ordinary Stop routes via systemd.
    "$rigyard_bin" scene autostart disable "$scene" ci
    systemctl is-active --quiet "$unit"
    "$rigyard_bin" scene stop "$scene" ci --non-interactive
    ! systemctl is-active --quiet "$unit"
    "$rigyard_bin" scene autostart enable "$scene" ci --non-interactive --now
    # Stop does not require the scenario YAML to remain readable.
    mv config/scenarios.yaml config/scenarios.saved
    "$rigyard_bin" scene autostart disable --unit "$unit" --now
    mv config/scenarios.saved config/scenarios.yaml
    [[ -z "$(find .rigyard/runs -name '*.json' -print -quit)" ]]
done

# A failed launch must be reported and cleaned up by ExecStopPost.
sed -i 's/echo scenario-ready; sleep 300/exit 37/' config/scenarios.yaml
"$rigyard_bin" scene autostart enable existing ci --non-interactive
if sudo systemctl start "${units[0]}"; then
    printf 'A failing boot scene was reported as successful.\n' >&2
    exit 1
fi
[[ "$(systemctl show "${units[0]}" --property=Result --value)" != success ]]
[[ "$(docker inspect --format '{{.State.Running}}' rigyard-ci-smoke)" == false ]]
[[ -z "$(find .rigyard/runs -name '*.json' -print -quit)" ]]
printf 'Systemd autostart smoke test passed.\n'
