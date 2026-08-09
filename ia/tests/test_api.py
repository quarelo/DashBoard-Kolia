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


def test_failed_analysis_response_exposes_error_message(monkeypatch):
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "analyze_meeting",
        lambda _db, payload: SimpleNamespace(
            id=UUID("66666666-6666-6666-6666-666666666666"),
            external_meeting_id=payload.meeting_id,
            status="FAILED",
            total_tokens=7,
            total_chunks=1,
            final_summary=None,
            error_message="JSON inválido",
        ),
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

    assert response.status_code == 200
    assert response.json()["error_message"] == "JSON inválido"
