import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from src.app.core.database import Base
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services.analysis_service import prepare_analysis


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'submissions.sqlite'}",
        execution_options={"schema_translate_map": {"ai": None}},
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture
def payload():
    return AnalyzeRequest(
        meeting_id=uuid4(), title="Contrato",
        transcription="[LOCUTOR 1]: Precisamos de 20 licenças até sexta-feira.",
    )


def _submission_api():
    # Resolve lazily so missing production behavior is an explicit test failure.
    from src.app.services import analysis_submission
    return analysis_submission.submit_idempotent, analysis_submission.SubmissionConflict


def test_repeat_returns_original_analysis_without_new_chunks_or_worker_work(sessions, payload):
    submit_idempotent, _ = _submission_api()
    submitted = []
    with sessions() as db:
        first = submit_idempotent(db, payload, "a" * 64, prepare_analysis, submitted.append)
        first_id = first.id
    with sessions() as db:
        second = submit_idempotent(db, payload, "a" * 64, prepare_analysis, submitted.append)
        assert second.id == first_id
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 1
        assert db.scalar(select(func.count()).select_from(MeetingChunk)) == 1
    assert submitted == [first_id]


@pytest.mark.parametrize("field,value", [
    ("title", "Outro contrato"), ("transcription", "Outra conversa."),
    ("meeting_id", uuid4()), ("user_id", uuid4()),
])
def test_reusing_key_with_changed_payload_conflicts(sessions, payload, field, value):
    submit_idempotent, conflict = _submission_api()
    submitted = []
    with sessions() as db:
        submit_idempotent(db, payload, "b" * 64, prepare_analysis, submitted.append)
    with sessions() as db, pytest.raises(conflict):
        submit_idempotent(db, payload.model_copy(update={field: value}), "b" * 64,
                          prepare_analysis, submitted.append)
    assert len(submitted) == 1


def test_failed_preparation_leaves_durable_claim_and_blocks_retry(sessions, payload):
    submit_idempotent, conflict = _submission_api()
    def failed_prepare(db, request, **kwargs):
        raise RuntimeError("process interrupted before creation")

    submitted = []
    with sessions() as db, pytest.raises(RuntimeError):
        submit_idempotent(db, payload, "c" * 64, failed_prepare, submitted.append)
    with sessions() as db, pytest.raises(conflict):
        submit_idempotent(db, payload, "c" * 64, prepare_analysis, submitted.append)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 0
    assert submitted == []


def test_crash_after_creation_commit_replays_persisted_analysis(sessions, payload):
    submit_idempotent, _ = _submission_api()
    created = []
    def interrupted_prepare(db, request, **kwargs):
        analysis = prepare_analysis(db, request, **kwargs)
        created.append(analysis.id)
        raise RuntimeError("process interrupted after creation commit")

    submitted = []
    with sessions() as db, pytest.raises(RuntimeError):
        submit_idempotent(db, payload, "1" * 64, interrupted_prepare, submitted.append)
    with sessions() as db:
        replay = submit_idempotent(db, payload, "1" * 64, prepare_analysis, submitted.append)
        assert replay.id == created[0]
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 1
        assert db.scalar(select(func.count()).select_from(MeetingChunk)) == 1
    assert submitted == []


def test_chunk_creation_failure_rolls_back_analysis_and_mapping_together(sessions, payload):
    from src.app.models.submission import AnalysisSubmission
    submit_idempotent, conflict = _submission_api()
    def fail_chunk_insert(_mapper, _connection, _chunk):
        raise RuntimeError("chunk persistence interrupted")

    event.listen(MeetingChunk, "before_insert", fail_chunk_insert)
    try:
        with sessions() as db, pytest.raises(RuntimeError):
            submit_idempotent(db, payload, "2" * 64, prepare_analysis, lambda _: None)
    finally:
        event.remove(MeetingChunk, "before_insert", fail_chunk_insert)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 0
        assert db.scalar(select(func.count()).select_from(MeetingChunk)) == 0
        assert db.get(AnalysisSubmission, "2" * 64).analysis_id is None
        with pytest.raises(conflict):
            submit_idempotent(db, payload, "2" * 64, prepare_analysis, lambda _: None)


def test_queue_failure_preserves_mapping_for_retry_and_worker_recovery(sessions, payload):
    submit_idempotent, _ = _submission_api()
    def failed_submit(_analysis_id):
        raise RuntimeError("queue interrupted")

    with sessions() as db, pytest.raises(RuntimeError):
        submit_idempotent(db, payload, "d" * 64, prepare_analysis, failed_submit)
    submitted = []
    with sessions() as db:
        analysis = submit_idempotent(db, payload, "d" * 64, prepare_analysis, submitted.append)
        assert analysis.status == "PROCESSING"
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 1
    assert submitted == []
    from src.app.services.analysis_worker import AnalysisWorker
    worker = AnalysisWorker(sessions)
    worker.recover()
    assert worker._queue.get_nowait() == analysis.id


def test_concurrent_request_cannot_prepare_while_owner_is_creating(sessions, payload):
    submit_idempotent, conflict = _submission_api()
    creating, release = Event(), Event()
    submitted = []
    def slow_prepare(db, request, **kwargs):
        creating.set()
        assert release.wait(timeout=10)
        return prepare_analysis(db, request, **kwargs)

    def owner():
        with sessions() as db:
            return submit_idempotent(db, payload, "e" * 64, slow_prepare, submitted.append).id

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(owner)
        try:
            assert creating.wait(timeout=10)
            with sessions() as db, pytest.raises(conflict):
                submit_idempotent(db, payload, "e" * 64, prepare_analysis, submitted.append)
        finally:
            release.set()
        first_id = pending.result(timeout=10)
    assert submitted == [first_id]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 1


@pytest.mark.parametrize("key", ["", "A" * 64, "f" * 63, "g" * 64, "f" * 64 + "\n"])
def test_invalid_key_never_creates_analysis(sessions, payload, key):
    submit_idempotent, _ = _submission_api()
    with sessions() as db, pytest.raises(ValueError):
        submit_idempotent(db, payload, key, prepare_analysis, lambda _: None)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 0


def test_analisar_header_deduplicates_and_rejects_payload_conflict(sessions, payload, monkeypatch):
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from src.app import main
    from src.app.core.database import get_db

    submitted = []
    monkeypatch.setattr(main, "analysis_worker", SimpleNamespace(submit=submitted.append))
    def get_test_db():
        with sessions() as db:
            yield db
    main.app.dependency_overrides[get_db] = get_test_db
    client = TestClient(main.app)
    try:
        # /analisar now requires a backend-issued token alongside the key.
        import jwt
        from src.app.core.config import settings
        auth = "Bearer " + jwt.encode({"sub": "test@kolia.com"},
                                      settings.secret_key, algorithm=settings.algorithm)
        headers = {"Idempotency-Key": "f" * 64, "Authorization": auth}
        first = client.post("/analisar", headers=headers, json=payload.model_dump(mode="json"))
        with sessions() as db:
            chunk = db.scalar(select(MeetingChunk))
            chunk.chunk_summary = {"resumo_chunk": "20 licenças até sexta-feira"}
            db.commit()
        second = client.post("/analisar", headers=headers, json=payload.model_dump(mode="json"))
        changed = payload.model_copy(update={"title": "Alterada"})
        conflict = client.post("/analisar", headers=headers, json=changed.model_dump(mode="json"))
        invalid = client.post("/analisar", headers={"Idempotency-Key": "invalid", "Authorization": auth},
                              json=payload.model_dump(mode="json"))
    finally:
        main.app.dependency_overrides.clear()
    assert first.status_code == second.status_code == 202
    assert first.json()["analysis_id"] == second.json()["analysis_id"]
    assert second.json()["processed_chunks"] == 1
    assert second.json()["progress_percent"] == 100.0
    assert conflict.status_code == 409
    assert invalid.status_code == 422
    assert len(submitted) == 1


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL URL not configured")
def test_postgresql_concurrent_claim_and_durable_replay(payload):
    """Exercise PostgreSQL uniqueness/FK behavior without needing vector/LLM."""
    from src.app.models.submission import AnalysisSubmission
    submit_idempotent, conflict = _submission_api()
    schema = "submission_test_" + uuid4().hex
    engine = create_engine(
        os.environ["TEST_DATABASE_URL"],
        execution_options={"schema_translate_map": {"ai": schema}},
    )
    tables = [MeetingAnalysis.__table__, AnalysisSubmission.__table__]
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine)
    creating, release = Event(), Event()
    submitted = []

    def prepare(db, request, *, on_created=None):
        creating.set()
        assert release.wait(timeout=10)
        analysis = MeetingAnalysis(
            external_meeting_id=request.meeting_id, title=request.title,
            status="PROCESSING",
        )
        db.add(analysis)
        db.flush()
        if on_created:
            on_created(analysis)
        db.commit()
        return analysis

    def owner():
        with factory() as db:
            return submit_idempotent(db, payload, "a" * 64, prepare, submitted.append).id

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(owner)
            try:
                assert creating.wait(timeout=10)
                with factory() as db, pytest.raises(conflict):
                    submit_idempotent(db, payload, "a" * 64, prepare, submitted.append)
            finally:
                release.set()
            analysis_id = pending.result(timeout=10)
        with factory() as db:
            replay = submit_idempotent(db, payload, "a" * 64, prepare, submitted.append)
            assert replay.id == analysis_id
            assert db.scalar(select(func.count()).select_from(MeetingAnalysis)) == 1
            assert db.scalar(select(func.count()).select_from(AnalysisSubmission)) == 1
        assert submitted == [analysis_id]
    finally:
        Base.metadata.drop_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(DropSchema(schema))
        engine.dispose()
