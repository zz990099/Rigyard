#!/usr/bin/env bash
# Exercise an installed Rigyard wheel against a real Docker daemon and tmux.

set -Eeuo pipefail

project_template="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/project" && pwd -P)"
scratch_dir="$(mktemp -d)"
project="$scratch_dir/project"
cp -R -- "$project_template" "$project"
mkdir -p "$scratch_dir/tmux"
export TMUX_TMPDIR="$scratch_dir/tmux"
rigyard_bin="${RIGYARD_BIN:-rigyard}"

cleanup() {
    status=$?
    trap - EXIT
    (
        cd -- "$project"
        "$rigyard_bin" scene stop existing ci >/dev/null 2>&1 || true
        "$rigyard_bin" scene down compose ci >/dev/null 2>&1 || true
    )
    tmux kill-server >/dev/null 2>&1 || true
    docker compose -f "$project/compose.yaml" -p rigyard-ci-smoke-compose \
        down --remove-orphans >/dev/null 2>&1 || true
    docker rm -f rigyard-ci-smoke >/dev/null 2>&1 || true
    docker image rm rigyard/ci-smoke:local >/dev/null 2>&1 || true
    rm -rf -- "$scratch_dir"
    exit "$status"
}
trap cleanup EXIT

cd -- "$project"
"$rigyard_bin" validate
"$rigyard_bin" image build smoke --non-interactive
"$rigyard_bin" container create smoke --non-interactive
"$rigyard_bin" build smoke --non-interactive
"$rigyard_bin" test run smoke --non-interactive
"$rigyard_bin" test report smoke --non-interactive
"$rigyard_bin" task run smoke --non-interactive

# Build/test/task should recover a stopped container when start_container is enabled.
docker stop rigyard-ci-smoke >/dev/null
"$rigyard_bin" task run smoke --non-interactive
[[ "$(docker inspect --format '{{.State.Running}}' rigyard-ci-smoke)" == true ]]

"$rigyard_bin" scene start existing ci --no-attach --non-interactive
for attempt in {1..10}; do
    if "$rigyard_bin" scene logs existing ci --instance app --group main |
        grep -q scenario-ready; then
        break
    fi
    if [[ "$attempt" == 10 ]]; then
        printf 'The existing-container scenario produced no output.\n' >&2
        exit 1
    fi
    sleep 1
done
"$rigyard_bin" scene stop existing ci --non-interactive

docker compose version
"$rigyard_bin" scene start compose ci --no-attach --non-interactive
"$rigyard_bin" scene status compose ci --non-interactive
"$rigyard_bin" scene down compose ci --non-interactive
printf 'Docker and tmux smoke test passed.\n'
