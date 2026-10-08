#!/usr/bin/env python3
"""Capture PostgreSQL and local media backups without stopping the service."""

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--directory", default="backups")
parser.add_argument(
    "--database-only",
    action="store_true",
    help="For upgrading starter containers without a media volume.",
)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
directory = Path(args.directory).resolve()
directory.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for service, command, suffix in [
    (
        "db",
        ["sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
        ".dump",
    ),
    ("app", ["tar", "-C", "/data", "-czf", "-", "."], ".media.tar.gz"),
]:
    if args.database_only and service == "app":
        continue
    target = directory / (stamp + suffix)
    temporary = target.with_suffix(target.suffix + ".partial")
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                ["docker", "compose", "exec", "-T", service, *command],
                cwd=root,
                stdout=output,
                check=True,
            )
        temporary.replace(target)
        target.chmod(0o600)
        print(target)
    finally:
        temporary.unlink(missing_ok=True)
