#!/usr/bin/env python3
"""Restore a database backup into an explicitly chosen, empty PostgreSQL database."""

import argparse
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument(
        "--target",
        required=True,
        help="An existing EMPTY database on the Compose PostgreSQL service.",
    )
    parser.add_argument("--confirm-target", required=True, help="Repeat the target database name.")
    args = parser.parse_args()
    if args.target != args.confirm_target:
        parser.error("Confirmation must exactly match the target database name.")
    if not args.target.replace("_", "").isalnum():
        parser.error("Use a database name containing only letters, numbers, and underscores.")
    root = Path(__file__).resolve().parents[1]
    check = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema=\'public\'"',
            "sh",
            args.target,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if check.stdout.strip() != "0":
        parser.error("The target database must be empty; this tool never overwrites an existing database.")
    with args.backup.open("rb") as source:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --single-transaction',
                "sh",
                args.target,
            ],
            cwd=root,
            stdin=source,
            check=True,
        )
    print("Restored into " + args.target)


if __name__ == "__main__":
    main()
