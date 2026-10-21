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
    database_url: str = ""
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
    use_sqlite: bool = field(
        default_factory=lambda: os.getenv("MOSS_USE_SQLITE", "false").lower() in {"true", "1", "yes"}
    )
    otel_enabled: bool = field(default_factory=lambda: os.getenv("MOSS_OTEL_ENABLED", "false").lower() == "true")
    otel_endpoint: str = field(
        default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    )
    otel_service_name: str = field(default_factory=lambda: os.getenv("OTEL_SERVICE_NAME", "mosscms"))
    otel_sample_rate: float = field(default_factory=lambda: float(os.getenv("MOSS_OTEL_TRACES_SAMPLE_RATE", "0.1")))
    otel_metric_interval_ms: int = field(default_factory=lambda: int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "10000")))

    def __post_init__(self):
        if self.use_sqlite:
            self.database_url = f"sqlite:///{self.storage_dir / 'mosscms.db'}"
        elif not self.database_url:
            self.database_url = configured_database()

    def validate(self):
        if self.otel_enabled:
            from urllib.parse import urlsplit

            endpoint = urlsplit(self.otel_endpoint)
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise RuntimeError("OTEL_EXPORTER_OTLP_ENDPOINT must be an HTTP(S) base URL without credentials/query.")
            if not 0 <= self.otel_sample_rate <= 1:
                raise RuntimeError("MOSS_OTEL_TRACES_SAMPLE_RATE must be between 0 and 1.")
            if not 1000 <= self.otel_metric_interval_ms <= 3600000:
                raise RuntimeError("OTEL_METRIC_EXPORT_INTERVAL must be 1000–3600000 milliseconds.")
            if not self.otel_service_name or len(self.otel_service_name) > 100:
                raise RuntimeError("OTEL_SERVICE_NAME must contain 1–100 characters.")
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
            if url.drivername.startswith("sqlite"):
                if not self.use_sqlite:
                    raise RuntimeError("Production SQLite requires MOSS_USE_SQLITE=true.")
            elif url.password in {None, "", "change-me", "mosscms"}:
                raise RuntimeError("Production requires PostgreSQL and a non-default database password.")
        return self
