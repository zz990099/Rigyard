# SPDX-License-Identifier: MIT
# Copyright (c) 2026 zz990099

"""Smoke tests for the shell bootstrap and activation contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _fake_uv(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$UV_TEST_LOG"
case "$1 $2" in
    '--version ') echo 'uv 0.test' ;;
    'python install') [[ "$3" == 3.12 && "$4" == --no-bin ]] ;;
    'venv --managed-python')
        [[ "$3" == --python && "$4" == 3.12 ]]
        target="$5"
        mkdir -p "$target/bin"
        touch "$target/pyvenv.cfg"
        ln -s /usr/bin/true "$target/bin/python"
        printf 'export VIRTUAL_ENV="%s"\\nexport PATH="%s/bin:$PATH"\\n' \\
            "$target" "$target" > "$target/bin/activate"
        ;;
    'pip install')
        [[ "$3" == --python && "$4" == "$XDG_DATA_HOME/rigyard/venv/bin/python" ]]
        cat > "$XDG_DATA_HOME/rigyard/venv/bin/rigyard" <<'TOOL'
#!/usr/bin/env bash
echo 'rigyard 0.test'
TOOL
        chmod +x "$XDG_DATA_HOME/rigyard/venv/bin/rigyard"
        ;;
    *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_bootstrap_targets_dedicated_venv_and_activation_changes_shell(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_uv(bin_dir / "uv")
    data_home = tmp_path / "data home"
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "XDG_DATA_HOME": str(data_home),
        "UV_TEST_LOG": str(log),
        "CONDA_PREFIX": str(tmp_path / "unrelated-conda"),
        "NO_COLOR": "1",
    }
    first = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "██████╗" in first.stdout
    assert "Setup complete." in first.stdout
    assert "--python " + str(data_home / "rigyard/venv/bin/python") in log.read_text()

    subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap.sh")], env=env, capture_output=True, check=True
    )
    assert log.read_text().count("venv --managed-python") == 1

    env.pop("CONDA_PREFIX")
    activated = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && source "$1" && printf "active=%s\\n" "$VIRTUAL_ENV"',
            "bash",
            str(SCRIPTS / "activate.sh"),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"active={data_home}/rigyard/venv" in activated.stdout
    assert "already active" in activated.stdout


def test_activation_refuses_missing_environment_and_active_conda(tmp_path: Path) -> None:
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path)}
    command = ["bash", "-c", 'source "$1"', "bash", str(SCRIPTS / "activate.sh")]
    missing = subprocess.run(command, env=env, capture_output=True, text=True)
    assert missing.returncode == 1
    assert "bootstrap.sh" in missing.stderr

    venv = tmp_path / "rigyard/venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").touch()
    tool = venv / "bin/rigyard"
    tool.write_text("#!/usr/bin/env bash\necho 'rigyard 0.test'\n", encoding="utf-8")
    tool.chmod(0o755)
    env["CONDA_PREFIX"] = str(tmp_path / "conda")
    blocked = subprocess.run(command, env=env, capture_output=True, text=True)
    assert blocked.returncode == 1
    assert "Deactivate" in blocked.stderr

    direct = subprocess.run(
        ["bash", str(SCRIPTS / "activate.sh")], env=env, capture_output=True, text=True
    )
    assert direct.returncode == 2
    assert "source" in direct.stderr


def test_bootstrap_installs_uv_when_missing(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = tmp_path / "uv-to-install"
    _fake_uv(fake_uv)

    installer = tmp_path / "installer.sh"
    installer.write_text(
        '#!/bin/sh\nmkdir -p "$UV_INSTALL_DIR"\ncp "$UV_TEST_FAKE_UV" "$UV_INSTALL_DIR/uv"\n',
        encoding="utf-8",
    )
    curl = bin_dir / "curl"
    curl.write_text('#!/usr/bin/env bash\ncp "$UV_TEST_INSTALLER" "${@: -1}"\n', encoding="utf-8")
    curl.chmod(0o755)

    data_home = tmp_path / "data"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "XDG_DATA_HOME": str(data_home),
        "UV_TEST_INSTALLER": str(installer),
        "UV_TEST_FAKE_UV": str(fake_uv),
        "UV_TEST_LOG": str(tmp_path / "uv.log"),
    }
    completed = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap.sh")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Downloading the official uv installer" in completed.stdout
    assert (data_home / "rigyard/bin/uv").is_file()
