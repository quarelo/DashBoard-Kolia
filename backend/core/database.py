from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import settings

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

    DDL used to run here through `create_all()`, which only ever CREATEs — it
    silently skips a table that already exists, so a column added later never
    appeared and the app failed at runtime instead of at startup. Schema changes
    now live in `migrations/`; this only refuses to start against a stale database.
    """
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))
    with engine.connect() as connection:
        current = MigrationContext.configure(
            connection, opts={"version_table_schema": "core"},
        ).get_current_revision()
    head = script.get_current_head()
    if current != head:
        raise RuntimeError(
            f"Banco na revisão {current or 'nenhuma'}, esperado {head}. "
            "Rode 'alembic upgrade head' em backend/ antes de subir o serviço."
        )
