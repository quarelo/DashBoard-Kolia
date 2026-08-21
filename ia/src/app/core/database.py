from sqlalchemy import create_engine, text
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
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    import src.app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE ai.meeting_analyses ADD COLUMN IF NOT EXISTS "
            "summary_attempt_started_at TIMESTAMP WITH TIME ZONE"
        ))
        connection.execute(text(
            "ALTER TABLE ai.meeting_analyses ADD COLUMN IF NOT EXISTS "
            "summary_attempt_started_chunks INTEGER NOT NULL DEFAULT 0"
        ))
        connection.execute(text(
            "ALTER TABLE ai.meeting_analyses ADD COLUMN IF NOT EXISTS "
            "summary_stage TEXT NOT NULL DEFAULT 'PRELIMINARY'"
        ))
        connection.execute(text(
            "ALTER TABLE ai.meeting_analyses ADD COLUMN IF NOT EXISTS "
            "summary_is_final BOOLEAN NOT NULL DEFAULT false"
        ))
