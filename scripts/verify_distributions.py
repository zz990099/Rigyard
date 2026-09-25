"""Check the artifacts that will be uploaded to a package index."""

from __future__ import annotations

import argparse
import email
import re
import tarfile
import zipfile
from pathlib import Path


def verify(directory: Path, tag: str | None = None) -> str:
    wheels = list(directory.glob("rigyard-*.whl"))
    sdists = list(directory.glob("rigyard-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1 or len(list(directory.iterdir())) != 2:
        raise ValueError("expected exactly one Rigyard wheel and one source distribution")

    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("wheel must contain exactly one METADATA file")
        metadata = email.message_from_bytes(archive.read(metadata_names[0]))
        version = metadata.get("Version")
        if metadata.get("Name", "").lower() != "rigyard" or not version:
            raise ValueError("wheel name or version is invalid")
        if "rigyard/cli/main.py" not in names or "rigyard/version.py" not in names:
            raise ValueError("wheel is missing the CLI or version module")
        entry_points = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(entry_points) != 1 or b"rigyard = rigyard.cli.main:main" not in archive.read(
            entry_points[0]
        ):
            raise ValueError("wheel is missing the Rigyard console entry point")

    with tarfile.open(sdists[0], "r:gz") as archive:
        names = [member.name for member in archive.getmembers()]
        prefix = f"rigyard-{version}/"
        for required in ("README.md", "LICENSE", "pyproject.toml", "src/rigyard/version.py"):
            if prefix + required not in names:
                raise ValueError(f"source distribution is missing {required}")

    if not wheels[0].name.startswith(f"rigyard-{version}-") or not sdists[0].name.startswith(
        f"rigyard-{version}."
    ):
        raise ValueError("wheel and source distribution versions differ")
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError(f"release tag {tag!r} differs from artifact version {version!r}")

    if any(re.search(r"(^|/)(\.git|\.rigyard|__pycache__|\.env)(/|$)", name) for name in names):
        raise ValueError("source distribution contains local state or secret files")
    print(f"Verified wheel and source distribution for rigyard {version}")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag", help="require an exact match with the release tag")
    arguments = parser.parse_args()
    verify(arguments.directory, arguments.tag)
