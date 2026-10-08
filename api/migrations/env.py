from alembic import context
from sqlalchemy import create_engine

from app.models import Base

config = context.config
url = config.attributes.get("database_url") or config.get_main_option("sqlalchemy.url")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = config.attributes.get("engine") or create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
