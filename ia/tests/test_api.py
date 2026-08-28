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

    chunks = [
        SimpleNamespace(chunk_summary={"pontos_chave": ["fato"]}),
        SimpleNamespace(chunk_summary=None),
    ]
    response = main._detail(analysis, chunks)

    assert response.status == "DASHBOARD_READY_WITH_EMBEDDING_ERROR"
    assert response.final_summary == {"resumo_geral": "Disponível"}
    assert response.error_message == "embedding indisponível"
    assert response.processed_chunks == 1
    assert response.total_chunks == 2
    assert response.progress_percent == 50.0
    assert response.summary_progress_percent == 50.0
    assert response.embedding_progress_percent == 0.0
    assert response.summary_stage == "PARTIAL"
    assert response.summary_is_final is False
    assert response.is_partial is True
    assert response.estimated_seconds_remaining is None


def test_semantic_search_returns_ranked_evidence(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "search_analysis_chunks",
        lambda _db, current_id, query, top_k: {
            "analysis_id": current_id,
            "query": query,
            "ready": True,
            "results": [{
                "chunk_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                "chunk_index": 7,
                "excerpt": "substituição de 27 máquinas",
                "similarity": 0.91,
            }],
        },
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/buscar",
            json={"query": "quantas máquinas precisam ser trocadas?", "top_k": 3},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["results"][0]["chunk_index"] == 7
    assert response.json()["results"][0]["similarity"] == 0.91


def test_category_evidence_returns_grouped_semantic_context(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "search_analysis_categories",
        lambda _db, current_id, top_k: {
            "analysis_id": current_id,
            "ready": True,
            "categories": {
                "budget": [{
                    "chunk_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                    "chunk_index": 3,
                    "excerpt": "R$ 50 mil de investimento",
                    "similarity": 0.94,
                }],
            },
        },
    )
    try:
        response = client.get(
            f"/analises/{analysis_id}/evidencias", params={"top_k": 2}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["categories"]["budget"][0]["chunk_index"] == 3


def test_chat_returns_grounded_answer_with_server_citations(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, current_id, payload: {
            "analysis_id": current_id,
            "answer": "São 27 máquinas por incompatibilidade com Windows 11.",
            "citations": [{
                "chunk_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                "chunk_index": 48,
                "excerpt": "27 máquinas precisam ser substituídas para Windows 11",
                "similarity": 0.83,
            }],
            "grounded": True,
            "fallback_reason": None,
        },
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat",
            json={
                "question": "E qual foi o motivo?",
                "history": [
                    {"role": "user", "content": "Quantas máquinas serão trocadas?"},
                    {"role": "assistant", "content": "Serão 27 máquinas."},
                ],
                "top_k": 4,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert response.json()["citations"][0]["chunk_index"] == 48


def test_chat_returns_safe_http_200_fallback(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, current_id, payload: {
            "analysis_id": current_id,
            "answer": "Não encontrei essa informação na transcrição desta reunião.",
            "citations": [],
            "grounded": False,
            "fallback_reason": "insufficient_evidence",
        },
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat",
            json={"question": "Qual era a cor do carro do cliente?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert response.json()["fallback_reason"] == "insufficient_evidence"


def test_chat_maps_missing_analysis_to_404(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, _current_id, _payload: (_ for _ in ()).throw(
            ValueError("Análise não encontrada.")
        ),
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat", json={"question": "Qual produto?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Análise não encontrada."


def test_chat_maps_rag_not_ready_to_409(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, _current_id, _payload: (_ for _ in ()).throw(
            main.RagNotReadyError("Embeddings ainda não estão prontos.")
        ),
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat", json={"question": "Qual produto?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "Embeddings" in response.json()["detail"]


def test_chat_hides_unexpected_infrastructure_errors(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, _current_id, _payload: (_ for _ in ()).throw(
            RuntimeError("senha interna do banco")
        ),
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat", json={"question": "Qual produto?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat temporariamente indisponível."
    assert "senha" not in response.text


def test_chat_rejects_invalid_history_before_database_access():
    response = client.post(
        "/analises/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/chat",
        json={
            "question": "E quando?",
            "history": [{"role": "user", "content": "Quem ficou responsável?"}],
        },
    )

    assert response.status_code == 422
