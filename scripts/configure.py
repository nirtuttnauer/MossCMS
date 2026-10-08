#!/usr/bin/env python3
"""Create local configuration without overwriting existing secrets."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--existing-db",
    action="store_true",
    help="Preserve the original starter database password for development.",
)
parser.add_argument("--production", action="store_true")
parser.add_argument("--public-url", default="http://localhost:8000")
args = parser.parse_args()
if args.production and not args.public_url.startswith("https://"):
    parser.error("--production requires --public-url https://...")
root = Path(__file__).resolve().parents[1]
file = root / ".env"
values = {}
if file.exists():
    for line in file.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
for key, value in {
    "POSTGRES_DB": "mosscms",
    "POSTGRES_USER": "mosscms",
    "POSTGRES_PASSWORD": "change-me" if args.existing_db else secrets.token_urlsafe(32),
    "MOSS_SECRET_KEY": secrets.token_urlsafe(48),
    "MOSS_SETUP_TOKEN": secrets.token_urlsafe(32),
    "MOSS_ENV": "production" if args.production else "development",
    "MOSS_SKIP_AUTH": "false",
    "MOSS_PUBLIC_URL": args.public_url,
    "MOSS_ORIGINS": args.public_url
    if args.production
    else args.public_url + ",http://localhost:5173",
    "MOSS_PORT": "8000",
}.items():
    values.setdefault(key, value)
if args.production:
    values["MOSS_ENV"] = "production"
    values["MOSS_SKIP_AUTH"] = "false"
    values["MOSS_PUBLIC_URL"] = args.public_url
    values["MOSS_ORIGINS"] = args.public_url
if args.production and values["POSTGRES_PASSWORD"] == "change-me":
    parser.error(
        "Existing development credentials cannot be used in production; rotate the database password first."
    )
file.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
file.chmod(0o600)
print(
    "Configuration saved to .env. Use MOSS_SETUP_TOKEN from that file for the first administrator setup."
)
