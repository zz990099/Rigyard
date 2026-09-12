from pathlib import Path

from toolchain.cli import run


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_and_inspect(tmp_path: Path, capsys) -> None:
    schema = write(
        tmp_path / "schema.yaml",
        "version: 1\nparameters:\n  debug:\n    type: bool\n    default: false\n",
    )
    assert run(["validate", str(schema)]) == 0
    assert "OK:" in capsys.readouterr().out

    assert run(["inspect", str(schema), "--format", "json"]) == 0
    assert '"TOOL_PARAM_DEBUG"' in capsys.readouterr().out


def test_resolve_with_values_and_cli_override(tmp_path: Path, capsys, monkeypatch) -> None:
    schema = write(
        tmp_path / "schema.yaml",
        "version: 1\nparameters:\n  count:\n    type: int\n    default: 1\n",
    )
    values = write(tmp_path / "values.yaml", "count: 2\n")
    monkeypatch.delenv("TOOL_PARAM_COUNT", raising=False)
    assert (
        run(
            [
                "resolve",
                str(schema),
                "--values",
                str(values),
                "--set",
                "count=4",
                "--non-interactive",
                "--with-sources",
                "--format",
                "json",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"value": 4' in output
    assert '"source": "cli"' in output


def test_noninteractive_failure_exit_code(tmp_path: Path, capsys) -> None:
    schema = write(
        tmp_path / "schema.yaml",
        "version: 1\nparameters:\n  required_value:\n    required: true\n",
    )
    assert run(["resolve", str(schema), "--non-interactive"]) == 3
    assert "missing required" in capsys.readouterr().err

