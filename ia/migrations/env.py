"""Alembic environment for the IA service.

The version table lives in the `ai` schema; the backend keeps its own in `core`.
Both services share one database, so a version table each lets them be migrated
and deployed independently.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Models are imported as `src.app.…`, so the service root must be importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.core.config import settings  # noqa: E402
from src.app.core.database import Base  # noqa: E402
import src.app.models  # noqa: F401,E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata

SCHEMA = "ai"


def include_object(obj, name, type_, reflected, compare_to):
    """Autogenerate must ignore the backend's tables, which share this database."""
    if type_ == "table" and obj.schema not in (SCHEMA, None):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # The version table cannot live in a schema that does not exist yet, and
        # pgvector has to be present before any Vector column is created.
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=SCHEMA,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
