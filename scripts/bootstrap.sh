#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 zz990099

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly DATA_HOME="${XDG_DATA_HOME:-${HOME:?HOME must be set}/.local/share}"
readonly INSTALL_ROOT="$DATA_HOME/rigyard"
readonly VENV_DIR="$INSTALL_ROOT/venv"
readonly UV_INSTALL_DIR="$INSTALL_ROOT/bin"

if [[ "$DATA_HOME" != /* ]]; then
    printf 'Error: XDG_DATA_HOME must be an absolute path.\n' >&2
    exit 1
fi

if [[ -t 1 && "${TERM:-}" != dumb && ! ${NO_COLOR+x} ]]; then
    cyan=$'\033[1;36m'
    green=$'\033[1;32m'
    yellow=$'\033[1;33m'
    reset=$'\033[0m'
else
    cyan=''
    green=''
    yellow=''
    reset=''
fi

printf '%s' "$cyan"
cat <<'LOGO'
██████╗ ██╗ ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗
██╔══██╗██║██╔════╝ ╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗
██████╔╝██║██║  ███╗ ╚████╔╝ ███████║██████╔╝██║  ██║
██╔══██╗██║██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██║  ██║
██║  ██║██║╚██████╔╝   ██║   ██║  ██║██║  ██║██████╔╝
╚═╝  ╚═╝╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝
LOGO
printf '%s\n\n' "$reset"
printf '%s\n\n' '  Host setup  ·  uv-managed Python  ·  isolated Rigyard environment'

step() {
    printf '%s\n' "${cyan}[$1/4]${reset} $2"
}

ok() {
    printf '  %s✓%s %s\n' "$green" "$reset" "$1"
}

warn() {
    printf '  %s!%s %s\n' "$yellow" "$reset" "$1"
}

die() {
    printf '  Error: %s\n' "$1" >&2
    exit 1
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        warn 'Docker CLI not found; install Docker before running container operations.'
        return
    fi
    ok "Docker CLI available ($(docker --version 2>/dev/null || printf 'version unknown'))"

    # Limit daemon checks so an unreachable remote Docker host does not stall setup.
    if ! command -v timeout >/dev/null 2>&1; then
        warn 'timeout not found; Docker daemon check skipped.'
    elif timeout 8s docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
        ok 'Docker daemon accessible'
    else
        warn 'Docker daemon unavailable or timed out; check its service, context and permissions.'
    fi

    if docker compose version >/dev/null 2>&1; then
        ok 'Docker Compose v2 available'
    else
        warn 'Docker Compose v2 not found; required for Compose scenarios.'
    fi
}

download_installer() {
    local destination="$1"
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --silent --show-error --retry 3 \
            --connect-timeout 10 --max-time 120 \
            https://astral.sh/uv/install.sh --output "$destination"
    elif command -v wget >/dev/null 2>&1; then
        wget --quiet --tries=3 --timeout=30 \
            --output-document="$destination" https://astral.sh/uv/install.sh
    else
        die 'Install curl or wget to download uv, then rerun this script.'
    fi
}

step 1 'Checking host tools'
[[ "$(uname -s)" == Linux ]] || die 'This bootstrap currently supports Linux only.'
ok "Linux $(uname -m)"
check_docker
if command -v tmux >/dev/null 2>&1; then
    ok 'tmux available for scenarios'
else
    warn 'tmux not found; required only for scenario commands.'
fi
printf '\n'

step 2 'Preparing uv'
if command -v uv >/dev/null 2>&1; then
    uv_bin="$(command -v uv)"
elif [[ -x "$UV_INSTALL_DIR/uv" ]]; then
    uv_bin="$UV_INSTALL_DIR/uv"
else
    ok 'Downloading the official uv installer'
    mkdir -p -- "$UV_INSTALL_DIR"
    temporary_dir="$(mktemp -d)"
    trap 'rm -rf -- "$temporary_dir"' EXIT
    download_installer "$temporary_dir/install.sh"
    env UV_INSTALL_DIR="$UV_INSTALL_DIR" UV_NO_MODIFY_PATH=1 \
        sh "$temporary_dir/install.sh"
    uv_bin="$UV_INSTALL_DIR/uv"
fi
[[ -x "$uv_bin" ]] || die "uv executable not found at $uv_bin"
ok "$("$uv_bin" --version)"
printf '\n'

step 3 'Preparing the isolated Python environment'
if [[ -L "$VENV_DIR" ]]; then
    die "Refusing to replace a symbolic link: $VENV_DIR"
elif [[ -e "$VENV_DIR" ]]; then
    [[ -f "$VENV_DIR/pyvenv.cfg" && -x "$VENV_DIR/bin/python" ]] ||
        die "An incomplete or unrelated directory exists at $VENV_DIR"
    ok "Reusing $VENV_DIR"
else
    "$uv_bin" python install 3.12 --no-bin || die 'Could not install uv-managed Python 3.12.'
    "$uv_bin" venv --managed-python --python 3.12 "$VENV_DIR" ||
        die 'Could not create the Rigyard environment.'
    ok "Created $VENV_DIR"
fi
printf '\n'

step 4 'Installing Rigyard from this checkout'
# An explicit interpreter prevents active Conda and other venvs from changing the target.
"$uv_bin" pip install --python "$VENV_DIR/bin/python" \
    --reinstall-package rigyard "$REPO_ROOT" || die 'Rigyard installation failed.'
[[ -x "$VENV_DIR/bin/rigyard" ]] || die 'Rigyard executable was not installed.'
ok "$("$VENV_DIR/bin/rigyard" --version)"
printf '\n%s\n' "${green}Setup complete.${reset} Activate Rigyard in this terminal with:"
printf '  source %q\n' "$SCRIPT_DIR/activate.sh"
printf '\n%s\n' 'Docker and tmux warnings above do not prevent CLI installation.'
