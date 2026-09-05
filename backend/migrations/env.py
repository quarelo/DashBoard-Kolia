"""Alembic environment for the backend service.

The version table lives in the `core` schema, and the IA service keeps its own in
`ai`. Both services share one database, so giving each its own version table lets
them be migrated and deployed independently.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Modules here import each other with flat paths (`from core.config import ...`),
# so the service root has to be importable before anything else is loaded.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.database import Base  # noqa: E402
import models.meeting  # noqa: F401,E402
import models.user  # noqa: F401,E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata

SCHEMA = "core"
VERSION_TABLE_SCHEMA = "core"


def include_object(obj, name, type_, reflected, compare_to):
    """Autogenerate must ignore the IA's tables, which live in the same database."""
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
        version_table_schema=VERSION_TABLE_SCHEMA,
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
        # The version table cannot be created inside a schema that does not exist
        # yet, so the very first migration of a fresh database would fail without this.
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=VERSION_TABLE_SCHEMA,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
