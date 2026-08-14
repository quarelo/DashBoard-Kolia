from sqlalchemy import create_engine, text
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
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        
    import models.user
    Base.metadata.create_all(bind=engine)