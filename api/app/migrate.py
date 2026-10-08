from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text


def migrate(engine, revision="head"):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.attributes["engine"] = engine
    # Serialize schema upgrades for containers sharing a PostgreSQL database.
    if engine.dialect.name == "postgresql":
        with engine.connect() as lock:
            lock.execute(text("SELECT pg_advisory_lock(741582901)"))
            try:
                command.upgrade(config, revision)
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(741582901)"))
    else:
        command.upgrade(config, revision)
