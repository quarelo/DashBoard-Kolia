"""Excluir uma reunião apaga a análise no `ai` e a importação no `core`, numa transação.

É a exceção à fronteira dos schemas (CLAUDE.md, "Serviços"), então estes testes
precisam do schema `ai`. `ai_schema` cria o mínimo que a exclusão toca, com as
mesmas FKs das migrações da IA, só onde as tabelas ainda não existem: num banco
de teste com o schema real, é o real que vale.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

CSV = "ID_MEETING,ANON_TRANSCRICAO\n100,locutor_1 Precisamos de 20 licenças.\n".encode()

# Colunas NOT NULL e FKs de ia/migrations/versions 0001, 0003, 0004, 0007 e 0009.
AI_DDL = """
CREATE SCHEMA IF NOT EXISTS ai;
CREATE TABLE IF NOT EXISTS ai.meeting_analyses (
    id uuid PRIMARY KEY, external_meeting_id uuid NOT NULL, title text NOT NULL,
    status text NOT NULL, total_tokens integer NOT NULL, total_chunks integer NOT NULL);
CREATE TABLE IF NOT EXISTS ai.meeting_chunks (
    id uuid PRIMARY KEY,
    analysis_id uuid NOT NULL REFERENCES ai.meeting_analyses(id) ON DELETE CASCADE,
    external_meeting_id uuid NOT NULL, chunk_index integer NOT NULL,
    token_count integer NOT NULL, content text NOT NULL);
CREATE TABLE IF NOT EXISTS ai.chunk_passages (
    id uuid PRIMARY KEY,
    chunk_id uuid NOT NULL REFERENCES ai.meeting_chunks(id) ON DELETE CASCADE,
    analysis_id uuid NOT NULL, passage_index integer NOT NULL,
    content text NOT NULL, token_count integer NOT NULL);
CREATE TABLE IF NOT EXISTS ai.chat_conversations (
    id uuid PRIMARY KEY,
    analysis_id uuid NOT NULL REFERENCES ai.meeting_analyses(id) ON DELETE CASCADE,
    title text NOT NULL);
CREATE TABLE IF NOT EXISTS ai.chat_messages (
    id uuid PRIMARY KEY,
    analysis_id uuid NOT NULL REFERENCES ai.meeting_analyses(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES ai.chat_conversations(id) ON DELETE CASCADE,
    role text NOT NULL, content text NOT NULL);
CREATE TABLE IF NOT EXISTS ai.analysis_submissions (
    key varchar(64) PRIMARY KEY, payload_hash varchar(64) NOT NULL,
    analysis_id uuid REFERENCES ai.meeting_analyses(id) ON DELETE RESTRICT);
"""


def token_for(email):
    from core.security import create_access_token
    return "Bearer " + create_access_token({"sub": email})


@pytest.fixture
def client(database):
    from main import app
    from core.database import get_db

    factory, _ = database

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    api = TestClient(app)
    api.headers["Authorization"] = token_for("importer@example.com")
    yield api
    api.close()
    app.dependency_overrides.clear()


@pytest.fixture
def ai_schema(database):
    from services.meeting_deletion import AI_ROWS_BY_ANALYSIS

    factory, _ = database
    with factory() as db:
        db.execute(text(AI_DDL))
        for table, _column in AI_ROWS_BY_ANALYSIS:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
    return factory


def insert_analysis(factory, status="DONE"):
    """An analysis with one row in every `ai` table that hangs off it."""
    analysis_id = uuid4()
    ids = {"a": str(analysis_id), "c": str(uuid4()), "m": str(uuid4()),
           "p": str(uuid4()), "conv": str(uuid4()), "msg": str(uuid4()),
           "k": uuid4().hex * 2, "h": "0" * 64, "status": status}
    with factory() as db:
        for statement in (
            "INSERT INTO ai.meeting_analyses (id, external_meeting_id, title, status, total_tokens, total_chunks)"
            " VALUES (:a, :m, 'Reunião', :status, 3, 1)",
            "INSERT INTO ai.meeting_chunks (id, analysis_id, external_meeting_id, chunk_index, token_count, content)"
            " VALUES (:c, :a, :m, 1, 3, 'texto')",
            "INSERT INTO ai.chunk_passages (id, chunk_id, analysis_id, passage_index, content, token_count)"
            " VALUES (:p, :c, :a, 0, 'texto', 1)",
            "INSERT INTO ai.chat_conversations (id, analysis_id, title) VALUES (:conv, :a, 'Qual o prazo?')",
            "INSERT INTO ai.chat_messages (id, analysis_id, conversation_id, role, content)"
            " VALUES (:msg, :a, :conv, 'user', 'Qual o prazo?')",
            "INSERT INTO ai.analysis_submissions (key, payload_hash, analysis_id) VALUES (:k, :h, :a)",
        ):
            db.execute(text(statement), ids)
        db.commit()
    return analysis_id


def import_meeting(client, factory, analysis_id):
    from models.meeting import ImportedMeeting

    assert client.post("/api/imports", files={"file": ("m.csv", CSV)}).status_code == 201
    with factory() as db:
        db.scalar(select(ImportedMeeting)).analysis_id = analysis_id
        db.commit()


def ai_rows(factory, analysis_id):
    from services.meeting_deletion import AI_ROWS_BY_ANALYSIS

    with factory() as db:
        return {table: db.scalar(text(f"SELECT count(*) FROM {table} WHERE {column} = :id"),
                                 {"id": str(analysis_id)})
                for table, column in AI_ROWS_BY_ANALYSIS}


def promote(factory, email):
    from models.user import UserModel
    from schemas.user import RoleEnum

    with factory() as db:
        db.scalar(select(UserModel).where(UserModel.email == email)).role = RoleEnum.SALES_DIRECTOR
        db.commit()


def remaining(client):
    client.headers["Authorization"] = token_for("importer@example.com")
    return client.get("/api/meetings").json()["total"]


def test_owner_deletes_the_meeting_and_everything_the_ai_kept_of_it(client, ai_schema):
    analysis_id, other = insert_analysis(ai_schema), insert_analysis(ai_schema)
    import_meeting(client, ai_schema, analysis_id)

    response = client.delete(f"/api/dashboard/meetings/{analysis_id}")

    assert response.status_code == 204, response.text
    assert set(ai_rows(ai_schema, analysis_id).values()) == {0}
    assert set(ai_rows(ai_schema, other).values()) == {1}, "a outra análise não pode ser tocada"
    assert remaining(client) == 0


def test_analysis_still_processing_is_refused_and_nothing_is_deleted(client, ai_schema):
    """The IA worker may still be writing to it; deleting underneath would fail its
    next commit halfway."""
    analysis_id = insert_analysis(ai_schema, status="EMBEDDING")
    import_meeting(client, ai_schema, analysis_id)

    response = client.delete(f"/api/dashboard/meetings/{analysis_id}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ANALYSIS_IN_PROGRESS"
    assert set(ai_rows(ai_schema, analysis_id).values()) == {1}
    assert remaining(client) == 1


def test_failed_analysis_can_be_deleted(client, ai_schema):
    analysis_id = insert_analysis(ai_schema, status="FAILED_ANALYSIS")
    import_meeting(client, ai_schema, analysis_id)

    assert client.delete(f"/api/dashboard/meetings/{analysis_id}").status_code == 204
    assert set(ai_rows(ai_schema, analysis_id).values()) == {0}


def test_user_cannot_delete_a_meeting_someone_else_imported(client, ai_schema):
    analysis_id = insert_analysis(ai_schema)
    import_meeting(client, ai_schema, analysis_id)
    client.headers["Authorization"] = token_for("other@example.com")

    response = client.delete(f"/api/dashboard/meetings/{analysis_id}")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DELETE_FORBIDDEN"
    assert set(ai_rows(ai_schema, analysis_id).values()) == {1}
    assert remaining(client) == 1


def test_sales_director_deletes_any_meeting(client, ai_schema):
    analysis_id = insert_analysis(ai_schema)
    import_meeting(client, ai_schema, analysis_id)
    promote(ai_schema, "other@example.com")
    client.headers["Authorization"] = token_for("other@example.com")

    assert client.delete(f"/api/dashboard/meetings/{analysis_id}").status_code == 204
    assert set(ai_rows(ai_schema, analysis_id).values()) == {0}
    assert remaining(client) == 0


def test_analysis_sent_straight_to_the_ia_is_deleted_only_by_a_director(client, ai_schema):
    """No core row means no owner to check against."""
    analysis_id = insert_analysis(ai_schema)

    assert client.delete(f"/api/dashboard/meetings/{analysis_id}").status_code == 403
    promote(ai_schema, "importer@example.com")
    assert client.delete(f"/api/dashboard/meetings/{analysis_id}").status_code == 204
    assert set(ai_rows(ai_schema, analysis_id).values()) == {0}


def test_core_row_whose_analysis_is_already_gone_is_still_deleted(client, ai_schema):
    import_meeting(client, ai_schema, uuid4())
    analysis_id = client.get("/api/meetings").json()["items"][0]["analysis_id"]

    assert client.delete(f"/api/dashboard/meetings/{analysis_id}").status_code == 204
    assert remaining(client) == 0


def test_unknown_analysis_is_404(client, ai_schema):
    promote(ai_schema, "importer@example.com")

    assert client.delete(f"/api/dashboard/meetings/{uuid4()}").status_code == 404


def test_a_failure_midway_deletes_nothing(client, ai_schema):
    """One transaction: when the last DELETE is barred, the earlier ones come back.

    This is also the documented cost of the exception — an `ai` table left out of
    AI_ROWS_BY_ANALYSIS with a RESTRICT foreign key blocks the whole deletion.
    """
    analysis_id = insert_analysis(ai_schema)
    import_meeting(client, ai_schema, analysis_id)
    with ai_schema() as db:
        db.execute(text("CREATE TABLE ai.test_unlisted_child ("
                        "analysis_id uuid REFERENCES ai.meeting_analyses(id) ON DELETE RESTRICT)"))
        db.execute(text("INSERT INTO ai.test_unlisted_child VALUES (:id)"), {"id": str(analysis_id)})
        db.commit()
    try:
        with pytest.raises(IntegrityError):
            client.delete(f"/api/dashboard/meetings/{analysis_id}")
        assert set(ai_rows(ai_schema, analysis_id).values()) == {1}
        assert remaining(client) == 1
    finally:
        with ai_schema() as db:
            db.execute(text("DROP TABLE ai.test_unlisted_child"))
            db.commit()


def test_deletion_list_covers_every_ai_table_that_stores_analysis_rows(ai_schema):
    """Guards the cost of the exception: a new `ai` table tied to an analysis has to
    join AI_ROWS_BY_ANALYSIS, children before parents. Meaningful against a test
    database carrying the IA's real schema; the minimal one passes by construction."""
    from services.meeting_deletion import AI_ROWS_BY_ANALYSIS

    listed = [table for table, _column in AI_ROWS_BY_ANALYSIS]
    with ai_schema() as db:
        with_analysis_id = set(db.scalars(text(
            "SELECT 'ai.' || table_name FROM information_schema.columns"
            " WHERE table_schema = 'ai' AND column_name = 'analysis_id'")))
        foreign_keys = db.execute(text(
            "SELECT 'ai.' || child.relname, 'ai.' || parent.relname FROM pg_constraint c"
            " JOIN pg_class child ON child.oid = c.conrelid"
            " JOIN pg_class parent ON parent.oid = c.confrelid"
            " JOIN pg_namespace n ON n.oid = child.relnamespace"
            " WHERE c.contype = 'f' AND n.nspname = 'ai'")).all()

    referencing_analysis = {child for child, parent in foreign_keys if parent == "ai.meeting_analyses"}
    assert with_analysis_id | referencing_analysis <= set(listed)
    for child, parent in foreign_keys:
        if child in listed and parent in listed and child != parent:
            assert listed.index(child) < listed.index(parent), f"{child} precisa vir antes de {parent}"


def test_browser_preflight_allows_delete():
    """CORS listed only GET and POST; the browser would block the request before it
    reached the route, and the button would fail with a network error."""
    from core.config import settings
    from main import app

    response = TestClient(app).options("/api/dashboard/meetings/x", headers={
        "Origin": settings.cors_origins[0],
        "Access-Control-Request-Method": "DELETE",
    })

    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
