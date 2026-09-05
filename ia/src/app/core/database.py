from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """Verify the schema is migrated; never create or alter it.

    This used to run `create_all()` plus a block of `ALTER TABLE ... ADD COLUMN
    IF NOT EXISTS` on every startup — DDL executed by the application itself, with
    no record of what had been applied. Schema changes now live in `migrations/`;
    this only refuses to start against a stale database.
    """
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[3]
    script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))
    with engine.connect() as connection:
        current = MigrationContext.configure(
            connection, opts={"version_table_schema": "ai"},
        ).get_current_revision()
    head = script.get_current_head()
    if current != head:
        raise RuntimeError(
            f"Banco na revisão {current or 'nenhuma'}, esperado {head}. "
            "Rode 'alembic upgrade head' em ia/ antes de subir o serviço."
        )
