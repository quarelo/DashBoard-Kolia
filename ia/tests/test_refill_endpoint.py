"""On-demand refill: the model is asked again only for what an analysis left blank.

Manual by design. Refilling in the pipeline would pay an extra call per analysis to
fill gaps that are usually correct — a transcript that never names a product should
keep `produto` empty. Here a person looked at the card, judged the gap wrong, and
asked; they also see whatever comes back.
"""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.app.main as main
from src.app.core.config import settings
from src.app.core.database import Base, get_db
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services import llm_service


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


CONTRATO = {name: [] for name in llm_service.FINAL_SUMMARY_SCHEMA["required"]}


def auth():
    import jwt
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": "t@kolia.com"}, settings.secret_key, algorithm=settings.algorithm)}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool,
                           execution_options={"schema_translate_map": {"ai": None}})
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    main.app.dependency_overrides[get_db] = lambda: db
    api = TestClient(main.app)
    yield api
    api.close()
    main.app.dependency_overrides.clear()


def make(db, resumo, *, final=True, com_chunk=True):
    analysis = MeetingAnalysis(
        external_meeting_id=uuid.uuid4(), title="t", status="DONE", total_chunks=1,
        final_summary=resumo, summary_is_final=final)
    db.add(analysis)
    db.commit()
    if com_chunk:
        db.add(MeetingChunk(analysis_id=analysis.id,
                            external_meeting_id=analysis.external_meeting_id,
                            chunk_index=1, token_count=10, content="texto",
                            chunk_summary={"pontos_chave": ["PRODUTO: TOTVS ERP"]}))
        db.commit()
    return analysis


def test_refills_only_the_empty_fields_and_keeps_the_rest(db, client, monkeypatch):
    resumo = {**CONTRATO, "produto": ["TOTVS CRM"], "persona": []}
    analysis = make(db, resumo)
    monkeypatch.setattr(main, "complete_missing_fields",
                        lambda s, c, **kw: {**s, "persona": ["gestor"]})

    body = client.post(f"/analises/{analysis.id}/recompletar", headers=auth()).json()

    assert body["final_summary"]["persona"] == ["gestor"]
    assert body["final_summary"]["produto"] == ["TOTVS CRM"], "não sobrescreve o preenchido"


def test_nothing_missing_returns_the_analysis_without_calling_the_model(db, client, monkeypatch):
    analysis = make(db, {**CONTRATO, **{n: ["x"] for n in CONTRATO}})

    def explode(*_a, **_k):
        raise AssertionError("não deveria chamar o modelo")

    monkeypatch.setattr(main, "complete_missing_fields", explode)
    assert client.post(f"/analises/{analysis.id}/recompletar", headers=auth()).status_code == 200


def test_requires_a_token(db, client):
    analysis = make(db, dict(CONTRATO))
    assert client.post(f"/analises/{analysis.id}/recompletar").status_code == 401


def test_unfinished_analysis_is_refused(db, client):
    analysis = make(db, dict(CONTRATO), final=False)
    response = client.post(f"/analises/{analysis.id}/recompletar", headers=auth())
    assert response.status_code == 409


def test_without_stored_chunk_summaries_it_refuses_instead_of_inventing(db, client):
    analysis = make(db, dict(CONTRATO), com_chunk=False)
    response = client.post(f"/analises/{analysis.id}/recompletar", headers=auth())
    assert response.status_code == 409


def test_unknown_analysis_is_404(client):
    assert client.post(f"/analises/{uuid.uuid4()}/recompletar",
                       headers=auth()).status_code == 404


def test_model_failure_is_reported_not_swallowed(db, client, monkeypatch):
    analysis = make(db, dict(CONTRATO))

    def falha(*_a, **_k):
        raise llm_service.OllamaError("Ollama fora do ar")

    monkeypatch.setattr(main, "complete_missing_fields", falha)
    assert client.post(f"/analises/{analysis.id}/recompletar",
                       headers=auth()).status_code == 503


def test_empty_collections_count_as_missing_only_when_asked(db):
    resumo = {**CONTRATO, "produto": ["TOTVS"], "persona": []}
    assert "persona" not in llm_service.missing_fields(resumo)
    assert "persona" in llm_service.missing_fields(resumo, include_empty=True)
    assert "produto" not in llm_service.missing_fields(resumo, include_empty=True)
