import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", os.getenv("TEST_DATABASE_URL", "sqlite://"))
os.environ.setdefault("SECRET_KEY", "test-key-not-used-outside-isolated-tests-123456789")


@pytest.fixture
def database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated kolia_import_test database")
    parsed = make_url(url)
    if not (parsed.database or "").startswith("kolia_import_test"):
        pytest.fail("Integration tests require a disposable kolia_import_test database")
    from core.database import Base
    from models.meeting import ImportedMeeting, MeetingImport
    from models.user import UserModel

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        user = UserModel(name="Importer", email="importer@example.com", password="unused")
        other = UserModel(name="Other", email="other@example.com", password="unused")
        db.add_all([user, other])
        db.commit()
        ids = (user.id, other.id)
    yield factory, ids
    engine.dispose()
