"""Validated application configuration; no credentials are compiled into the image."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def configured_database():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.getenv("POSTGRES_HOST"):
        from sqlalchemy import URL

        return URL.create(
            "postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            database=os.environ["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
    return "sqlite:///./mosscms.db"


def normalized_origins(origins: list[str], environment: str) -> list[str]:
    origins = [origin.rstrip("/") for origin in origins if origin]
    if environment == "development":
        expanded = list(origins)
        for o in origins:
            if "://localhost" in o:
                expanded.append(o.replace("://localhost", "://127.0.0.1"))
            elif "://127.0.0.1" in o:
                expanded.append(o.replace("://127.0.0.1", "://localhost"))
        origins = list(dict.fromkeys(expanded))
    return origins


@dataclass
class Settings:
    database_url: str = field(default_factory=configured_database)
    environment: str = field(default_factory=lambda: os.getenv("MOSS_ENV", "development"))
    skip_auth: bool = field(
        default_factory=lambda: os.getenv("MOSS_SKIP_AUTH", "false").lower() in {"true", "1", "yes"}
    )
    secret: str = field(default_factory=lambda: os.getenv("MOSS_SECRET_KEY", ""))
    setup_token: str = field(default_factory=lambda: os.getenv("MOSS_SETUP_TOKEN", ""))
    origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "MOSS_ORIGINS",
            "http://localhost:8001,http://127.0.0.1:8001,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
    )
    storage_dir: Path = field(default_factory=lambda: Path(os.getenv("MOSS_STORAGE_DIR", "./data")))
    public_url: str = field(default_factory=lambda: os.getenv("MOSS_PUBLIC_URL", "http://localhost:8001"))
    s3_bucket: str = field(default_factory=lambda: os.getenv("MOSS_S3_BUCKET", ""))
    s3_endpoint: str | None = field(default_factory=lambda: os.getenv("MOSS_S3_ENDPOINT") or None)
    webhook_origins: list[str] = field(
        default_factory=lambda: [x.rstrip("/") for x in os.getenv("MOSS_WEBHOOK_ORIGINS", "").split(",") if x]
    )
    max_upload: int = 20 * 1024 * 1024

    def validate(self):
        if self.skip_auth and self.environment != "development":
            raise RuntimeError("MOSS_SKIP_AUTH is only available when MOSS_ENV=development.")
        if len(self.secret) < 32 or len(self.setup_token) < 24:
            raise RuntimeError(
                "Set MOSS_SECRET_KEY (32+ characters) and MOSS_SETUP_TOKEN (24+ characters). Run scripts/configure.py."
            )
        self.origins = normalized_origins(self.origins, self.environment)
        if not self.origins or "*" in self.origins:
            raise RuntimeError("MOSS_ORIGINS must contain explicit trusted origins.")
        if self.environment == "production":
            from sqlalchemy.engine import make_url

            url = make_url(self.database_url)
            if url.drivername.startswith("sqlite") or url.password in {None, "", "change-me", "mosscms"}:
                raise RuntimeError("Production requires PostgreSQL and a non-default database password.")
        return self
