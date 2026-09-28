# SPDX-License-Identifier: MIT
# Copyright (c) 2026 zz990099

"""Exercise the standalone PyPI bootstrap without network or a checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/bootstrap_from_pypi.sh"


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
        ;;
    'pip install')
        [[ "$3" == --python && "$4" == "$XDG_DATA_HOME/rigyard/venv/bin/python" ]]
        [[ "$5" == --upgrade-package && "$6" == rigyard ]]
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


def _env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
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
    return env, data_home, log


def test_installs_pypi_package_without_checkout_or_activation(tmp_path: Path) -> None:
    env, data_home, log = _env(tmp_path)
    detached_script = tmp_path / "downloaded.sh"
    detached_script.write_bytes(SCRIPT.read_bytes())
    command = ["bash", str(detached_script)]

    first = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert "Setup complete." in first.stdout
    assert str(data_home / "rigyard/venv/bin/rigyard").replace(" ", "\\ ") in first.stdout
    assert "source " not in first.stdout
    assert f"--upgrade-package rigyard rigyard\n" in log.read_text()

    second = subprocess.run(
        [*command, "--version", "1.0.0"], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert second.returncode == 0, second.stderr
    assert log.read_text().count("venv --managed-python") == 1
    assert "--upgrade-package rigyard rigyard==1.0.0\n" in log.read_text()


def test_rejects_invalid_arguments_and_unrelated_environment(tmp_path: Path) -> None:
    env, data_home, log = _env(tmp_path)
    missing_version = subprocess.run(
        ["bash", str(SCRIPT), "--version"], env=env, capture_output=True, text=True
    )
    assert missing_version.returncode == 2
    assert not log.exists()

    venv = data_home / "rigyard/venv"
    venv.mkdir(parents=True)
    unrelated = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert unrelated.returncode != 0
    assert "incomplete or unrelated" in unrelated.stderr
    assert not log.exists() or "pip install" not in log.read_text()


def test_downloads_uv_without_python_or_checkout(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = tmp_path / "uv-to-install"
    _fake_uv(fake_uv)
    installer = tmp_path / "uv-installer.sh"
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
    detached_script = tmp_path / "downloaded.sh"
    detached_script.write_bytes(SCRIPT.read_bytes())
    result = subprocess.run(
        ["bash", str(detached_script)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "Downloading the official uv installer" in result.stdout
    assert (data_home / "rigyard/bin/uv").is_file()
    assert "--upgrade-package rigyard rigyard\n" in (tmp_path / "uv.log").read_text()
