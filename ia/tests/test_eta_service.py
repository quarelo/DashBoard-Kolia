"""Estimates are advisory, so these pin the properties that must not break:
never negative, never claim measurement without samples, and robust to the junk
rows real history contains."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from src.app.core.database import Base
from src.app.models.analysis import MeetingAnalysis
from src.app.services import eta_service
from src.app.services.eta_service import (
    Calibration, calibrate, estimate_analysis, estimate_backlog, estimate_batch,
)

@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


BASE = datetime(2026, 8, 19, 12, 0, 0)

def auth_header() -> dict:
    """Routes that expose analysis data now require a backend-issued token."""
    import jwt
    from src.app.core.config import settings

    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": "test@kolia.com"}, settings.secret_key, algorithm=settings.algorithm)}



@pytest.fixture
def db():
    # TestClient serves from another thread, so the in-memory database has to be
    # one shared connection rather than one per thread.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        execution_options={"schema_translate_map": {"ai": None}})
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        yield session
    engine.dispose()


def add(db, chunks, seconds, status="DONE", offset_minutes=0):
    started = BASE + timedelta(minutes=offset_minutes)
    analysis = MeetingAnalysis(
        external_meeting_id=uuid4(),
        title="t", status=status, total_chunks=chunks, total_tokens=chunks * 2000,
        created_at=started, updated_at=started + timedelta(seconds=seconds))
    db.add(analysis)
    db.commit()
    return analysis


def test_without_history_the_estimate_is_flagged_as_not_measured(db):
    calibration = calibrate(db)
    assert calibration.measured is False
    assert calibration.sample_count == 0
    assert calibration.seconds_for(1) > 0


def test_fit_separates_fixed_overhead_from_per_chunk_cost(db):
    # duration = 20s overhead + 10s per chunk, exactly.
    for index, chunks in enumerate([1, 2, 4, 8, 16]):
        add(db, chunks, 20 + 10 * chunks, offset_minutes=index)
    calibration = calibrate(db)
    assert calibration.measured is True
    assert calibration.overhead_seconds == pytest.approx(20, abs=0.5)
    assert calibration.seconds_per_chunk == pytest.approx(10, abs=0.5)
    assert calibration.seconds_for(48) == pytest.approx(500, abs=2)


def test_small_runs_are_not_dragged_up_by_large_noisy_ones(db):
    """Regression: a global least-squares line over the real history predicted
    ~232s for a 1-chunk run whose own samples average ~32s — a 7x error at exactly
    the size a bulk CSV import uses. A measured size must answer from its own data."""
    for index, seconds in enumerate([28.5, 32.4, 33.6, 35.0]):
        add(db, 1, seconds, offset_minutes=index)
    for index, seconds in enumerate([1459.7, 1577.8]):
        add(db, 22, seconds, offset_minutes=10 + index)
    for index, seconds in enumerate([772.3, 790.1, 1309.1, 1563.9, 1932.2, 1984.3]):
        add(db, 48, seconds, offset_minutes=20 + index)

    calibration = calibrate(db)
    assert calibration.seconds_for(1) == pytest.approx(33.0, abs=2)
    assert calibration.seconds_for(48) == pytest.approx(1436, abs=50)
    # An unmeasured size between two measured ones interpolates its neighbours.
    assert 700 < calibration.seconds_for(35) < 1600


def test_runs_of_a_single_size_cannot_split_overhead_and_still_estimate(db):
    """Equal-sized runs give no leverage on the intercept; fall back to a rate."""
    for index in range(4):
        add(db, 1, 32, offset_minutes=index)
    calibration = calibrate(db)
    assert calibration.measured is True
    assert calibration.seconds_for(1) == pytest.approx(32, abs=1)


def test_absurd_durations_are_excluded_from_calibration(db):
    """A row whose updated_at drifted 44h later must not poison the fit."""
    for index, chunks in enumerate([1, 2, 4, 8]):
        add(db, chunks, 20 + 10 * chunks, offset_minutes=index)
    clean = calibrate(db)
    add(db, 0, 158_701, offset_minutes=99)       # 0 chunks, observed in real data
    add(db, 4, 60 * 60 * 24, offset_minutes=100)  # beyond MAX_SAMPLE_SECONDS
    assert calibrate(db).seconds_for(10) == pytest.approx(clean.seconds_for(10), abs=1)


def test_failed_runs_do_not_calibrate_anything(db):
    add(db, 4, 5, status="FAILED")
    add(db, 4, 5, status="FAILED_ANALYSIS")
    assert calibrate(db).measured is False


def test_remaining_never_goes_negative_for_an_overdue_run(db):
    stale = add(db, 1, 0, status="PROCESSING")
    stale.created_at = datetime(2020, 1, 1)
    db.commit()
    result = estimate_analysis(db, stale)
    assert result["estimated_seconds_remaining"] == 0.0
    assert result["elapsed_seconds"] > 0


def test_finished_analysis_reports_no_remaining_time(db):
    done = add(db, 2, 40)
    assert estimate_analysis(db, done)["estimated_seconds_remaining"] is None


def test_finished_analysis_reports_how_long_it_actually_took(db):
    """elapsed_seconds must be the run's own duration (created_at to
    updated_at), not "how long ago it finished" (created_at to now) — the
    fixture's BASE is weeks in the past, so a bug here would report an
    elapsed time in the millions of seconds instead of the 40 it took."""
    done = add(db, 2, 40)
    assert estimate_analysis(db, done)["elapsed_seconds"] == pytest.approx(40, abs=1)


def test_backlog_counts_only_unfinished_work(db):
    add(db, 4, 60)                       # DONE, must not count
    add(db, 3, 0, status="PENDING", offset_minutes=1)
    add(db, 2, 0, status="EMBEDDING", offset_minutes=2)
    backlog = estimate_backlog(db, concurrency=1)
    assert (backlog["pending_analyses"], backlog["pending_chunks"]) == (2, 5)
    assert backlog["estimated_seconds_remaining"] > 0


def test_backlog_divides_by_worker_concurrency(db):
    for index in range(4):
        add(db, 1, 0, status="PENDING", offset_minutes=index)
    serial = estimate_backlog(db, concurrency=1)["estimated_seconds_remaining"]
    parallel = estimate_backlog(db, concurrency=2)["estimated_seconds_remaining"]
    assert parallel == pytest.approx(serial / 2, abs=0.2)


def test_batch_estimate_scales_with_count(db):
    one = estimate_batch(db, analyses=1)["estimated_serial_seconds"]
    many = estimate_batch(db, analyses=500)["estimated_serial_seconds"]
    assert many == pytest.approx(one * 500, rel=1e-6)


def test_batch_estimate_matches_the_measured_csv_profile(db):
    """The 500 CSV meetings are one chunk each; calibrate on 1-chunk history."""
    for index in range(4):
        add(db, 1, 32, offset_minutes=index)
    result = estimate_batch(db, analyses=500, chunks_each=1, concurrency=1)
    assert result["estimated_seconds"] == pytest.approx(500 * 32, rel=0.05)
    assert result["calibration"]["measured"] is True


def test_endpoints_expose_queue_batch_and_per_analysis_estimates(db, monkeypatch):
    from fastapi.testclient import TestClient

    import src.app.main as main
    from src.app.core.database import get_db

    for index in range(4):
        add(db, 1, 32, offset_minutes=index)
    queued = add(db, 1, 0, status="PENDING", offset_minutes=10)

    main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(main.app)
        fila = client.get("/fila", headers=auth_header()).json()
        assert fila["pending_analyses"] == 1
        assert fila["estimated_seconds_remaining"] > 0

        lote = client.get("/estimativa", params={"analyses": 500}, headers=auth_header()).json()
        assert lote["analyses"] == 500
        assert lote["estimated_seconds"] == pytest.approx(500 * 32, rel=0.05)

        one = client.get(f"/analises/{queued.id}/estimativa", headers=auth_header()).json()
        assert one["status"] == "PENDING"
        assert one["estimated_seconds_remaining"] >= 0

        assert client.get(f"/analises/{uuid4()}/estimativa", headers=auth_header()).status_code == 404
        assert client.get("/estimativa", params={"analyses": 0}, headers=auth_header()).status_code == 422
    finally:
        main.app.dependency_overrides.clear()
