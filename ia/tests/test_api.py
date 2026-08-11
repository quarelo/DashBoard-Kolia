from fastapi.testclient import TestClient
from types import SimpleNamespace
from uuid import UUID

from src.app.core.database import get_db
from src.app import main
from src.app.main import app


client = TestClient(app)


def test_health_identifies_ia_service():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "kolia-ia-service",
    }


def test_analisar_rejects_invalid_payload_before_database_access():
    response = client.post(
        "/analisar",
        json={
            "meeting_id": "not-a-uuid",
            "title": "",
            "transcription": "",
        },
    )

    assert response.status_code == 422


def test_analisar_returns_accepted_and_queues_analysis(monkeypatch):
    analysis_id = UUID("66666666-6666-6666-6666-666666666666")
    submitted = []
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "prepare_analysis",
        lambda _db, payload: SimpleNamespace(
            id=analysis_id,
            external_meeting_id=payload.meeting_id,
            status="PROCESSING",
            total_tokens=7,
            total_chunks=1,
            final_summary=None,
            error_message=None,
        ),
    )
    monkeypatch.setattr(
        main,
        "analysis_worker",
        SimpleNamespace(submit=lambda current_id: submitted.append(current_id)),
    )
    try:
        response = client.post(
            "/analisar",
            json={
                "meeting_id": "55555555-5555-5555-5555-555555555555",
                "title": "Reunião com falha",
                "transcription": "Cliente relatou erro na integração.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["final_summary"] is None
    assert submitted == [analysis_id]


def test_dashboard_ready_analysis_exposes_summary():
    analysis = SimpleNamespace(
        id=UUID("88888888-8888-8888-8888-888888888888"),
        external_meeting_id=UUID("99999999-9999-9999-9999-999999999999"),
        external_user_id=None,
        title="Reunião pronta",
        status="DASHBOARD_READY_WITH_EMBEDDING_ERROR",
        total_tokens=10,
        total_chunks=2,
        final_summary={"resumo_geral": "Disponível"},
        error_message="embedding indisponível",
    )

    response = main._detail(analysis)

    assert response.status == "DASHBOARD_READY_WITH_EMBEDDING_ERROR"
    assert response.final_summary == {"resumo_geral": "Disponível"}
    assert response.error_message == "embedding indisponível"
