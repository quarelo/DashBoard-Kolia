from fastapi.testclient import TestClient

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
