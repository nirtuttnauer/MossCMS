#!/usr/bin/env python3
"""Restore local media into an empty assets volume without replacing existing files."""

import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("backup", type=Path)
parser.add_argument("--confirm-empty-volume", action="store_true", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
program = """
import pathlib, tarfile, sys
root = pathlib.Path('/data')
if any(root.iterdir()):
    sys.exit('The assets volume must be empty; existing files are never overwritten.')
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
    for member in archive:
        destination = (root / member.name).resolve()
        if not destination.is_relative_to(root) or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
            sys.exit('Invalid archive member.')
        archive.extract(member, root, filter='data')
print('Local media restored.')
"""
with args.backup.open("rb") as source:
    subprocess.run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "app",
            "-c",
            program,
        ],
        cwd=root,
        stdin=source,
        check=True,
    )
