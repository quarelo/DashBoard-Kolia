"""Type shims so the SQLite-backed tests can build the Postgres schema.

JSONB and TSVECTOR have no SQLite equivalent, and the suite creates the real
tables in memory. Registering the compilers once here keeps every test file from
repeating them — and keeps a new file from failing at collection for a type it
never mentions.
"""
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app.core.database import Base
import src.app.models  # noqa: F401  garante que as tabelas existam

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


@compiles(TSVECTOR, "sqlite")
def _sqlite_tsvector(_type, _compiler, **_kwargs):
    # Only the column has to exist; lexical search is exercised against Postgres.
    return "TEXT"


@event.listens_for(Engine, "connect")
def _sqlite_text_search_stubs(dbapi_connection, _record):
    """Teach SQLite the Postgres functions the generated column calls.

    `search_vector` is `GENERATED ALWAYS AS (to_tsvector('portuguese', content))`,
    so creating the table at all needs the function to exist. The stub returns the
    text unchanged: these tests build the schema and exercise the vector path,
    while lexical ranking is only meaningful against Postgres.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    # deterministic=True: SQLite refuses a generated column otherwise.
    dbapi_connection.create_function(
        "to_tsvector", 2, lambda _config, text: text, deterministic=True)


@pytest.fixture
def sqlite_db():
    """An empty in-memory session.

    _lexical_query counts passages to decide which terms discriminate; with a
    corpus this small it keeps every term, which is what these cases assert.
    """
    engine = create_engine(
        "sqlite://", execution_options={"schema_translate_map": {"ai": None}})
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        yield session
    engine.dispose()
