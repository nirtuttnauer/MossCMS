#!/usr/bin/env python3
"""Configure and start the local CMS, then hand setup to the operator."""

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    if not shutil.which("docker"):
        raise SystemExit("Install Docker with Compose and start Docker before running this command.")
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        subprocess.run(["docker", "info"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        raise SystemExit("Docker with Compose must be installed and running. Start Docker and try again.") from None
    subprocess.run([sys.executable, str(root / "scripts/configure.py"), *sys.argv[1:]], check=True)
    subprocess.run(
        [
            "docker",
            "compose",
            "up",
            "--build",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "app",
        ],
        cwd=root,
        check=True,
    )
    values = dict(
        line.split("=", 1)
        for line in (root / ".env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    # Compose readiness is authoritative; use the loopback port for this operator check.
    local_url = "http://127.0.0.1:" + values["MOSS_PORT"]
    try:
        with urllib.request.urlopen(local_url + "/auth/status", timeout=10) as response:
            initialized = json.load(response)["initialized"]
    except (urllib.error.URLError, KeyError):
        raise SystemExit(
            "Containers started. Check docker compose logs app; the local setup endpoint could not be reached."
        ) from None
    print("\nMossCMS is ready: " + values["MOSS_PUBLIC_URL"])
    if not initialized:
        print("Create your administrator and workspace in that browser page.")
        print("Private setup token (for the local operator only): " + values["MOSS_SETUP_TOKEN"])
    else:
        print("Sign in with your existing account. Existing content and credentials are retained.")


if __name__ == "__main__":
    main()
