#!/usr/bin/env python3
"""Create local configuration without overwriting existing secrets."""

import argparse
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--existing-db",
        action="store_true",
        help="Preserve the original starter database password for development.",
    )
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Use persistent SQLite instead of PostgreSQL.",
    )
    parser.add_argument(
        "--public-url",
        help="Canonical origin; local URLs also configure the host port.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Local host port (1–65535); reverse-proxy origins remain independent.",
    )
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = Path(__file__).resolve().parents[1]
    file = root / ".env"
    values = {}
    if file.exists():
        for line in file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    public_url = args.public_url or values.get(
        "MOSS_PUBLIC_URL",
        f"http://localhost:{args.port or values.get('MOSS_PORT', '8001')}",
    )
    try:
        origin = urlsplit(public_url)
        public_port = origin.port or (443 if origin.scheme == "https" else 80)
    except ValueError:
        parser.error("--public-url must have a valid port")
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        parser.error("--public-url must be an HTTP(S) origin without credentials, path, query or fragment")
    if args.production and origin.scheme != "https":
        parser.error("--production requires --public-url https://...")
    local = origin.hostname in {"localhost", "127.0.0.1", "::1"} and not args.production
    if local and args.port and args.public_url and args.port != public_port:
        parser.error("--port and the local --public-url port must agree")
    if local and args.port and not args.public_url:
        host = f"[{origin.hostname}]" if origin.hostname == "::1" else origin.hostname
        public_url = f"{origin.scheme}://{host}:{args.port}"
    public_url = public_url.rstrip("/")
    if args.port is not None or args.public_url and local:
        values["MOSS_PORT"] = str(args.port or public_port)
    if args.public_url or args.port and local:
        values["MOSS_PUBLIC_URL"] = public_url
        if local:
            values["MOSS_ORIGINS"] = public_url + ",http://localhost:5173,http://127.0.0.1:5173"
    for key, value in {
        "POSTGRES_DB": "mosscms",
        "POSTGRES_USER": "mosscms",
        "POSTGRES_PASSWORD": "change-me" if args.existing_db else secrets.token_urlsafe(32),
        "MOSS_SECRET_KEY": secrets.token_urlsafe(48),
        "MOSS_SETUP_TOKEN": secrets.token_urlsafe(32),
        "MOSS_ENV": "production" if args.production else "development",
        "MOSS_SKIP_AUTH": "false",
        "MOSS_USE_SQLITE": "false",
        "MOSS_PUBLIC_URL": public_url,
        "MOSS_ORIGINS": public_url if args.production else public_url + ",http://localhost:5173,http://127.0.0.1:5173",
        "MOSS_PORT": str(args.port or 8001),
    }.items():
        values.setdefault(key, value)
    if args.sqlite:
        values["MOSS_USE_SQLITE"] = "true"
    if args.production:
        values["MOSS_ENV"] = "production"
        values["MOSS_SKIP_AUTH"] = "false"
        values["MOSS_PUBLIC_URL"] = public_url
        values["MOSS_ORIGINS"] = public_url
    if (
        args.production
        and values["MOSS_USE_SQLITE"].lower() not in {"true", "1", "yes"}
        and values["POSTGRES_PASSWORD"] == "change-me"
    ):
        parser.error(
            "Existing development credentials cannot be used in production; rotate the database password first."
        )
    file.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    file.chmod(0o600)
    print("Configuration saved to .env. Use MOSS_SETUP_TOKEN from that file for the first administrator setup.")


if __name__ == "__main__":
    main()
