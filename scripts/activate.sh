#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 zz990099

# This file must be sourced so activation changes the calling shell.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'Run this script with: source %q\n' "$0" >&2
    exit 2
fi

_rigyard_activate() {
    local data_home="${XDG_DATA_HOME:-${HOME:?HOME must be set}/.local/share}"
    local venv_dir="$data_home/rigyard/venv"
    if [[ "$data_home" != /* ]]; then
        printf 'Error: XDG_DATA_HOME must be an absolute path.\n' >&2
        return 1
    fi
    if [[ ! -f "$venv_dir/pyvenv.cfg" || ! -x "$venv_dir/bin/rigyard" ]] ||
        ! "$venv_dir/bin/rigyard" --version >/dev/null 2>&1; then
        printf 'Rigyard environment is missing or incomplete. Run bash scripts/bootstrap.sh first.\n' >&2
        return 1
    fi
    if [[ "${VIRTUAL_ENV:-}" == "$venv_dir" ]]; then
        printf 'Rigyard environment is already active.\n'
        return 0
    fi
    if [[ -n "${VIRTUAL_ENV:-}" || -n "${CONDA_PREFIX:-}" ]]; then
        printf 'Deactivate the current Python or Conda environment before activating Rigyard.\n' >&2
        return 1
    fi
    # shellcheck source=/dev/null
    source "$venv_dir/bin/activate"
    printf 'Rigyard ready: %s\n' "$(rigyard --version)"
}

_rigyard_activate
_rigyard_status=$?
unset -f _rigyard_activate
return "$_rigyard_status"
