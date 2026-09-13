import jwt
from datetime import datetime
from fastapi.testclient import TestClient
from types import SimpleNamespace
from uuid import UUID

from src.app.core.config import settings
from src.app.core.database import get_db
from src.app import main
from src.app.main import app


client = TestClient(app)


def _auth_header() -> dict:
    token = jwt.encode({"sub": "test@kolia.com"}, settings.secret_key, algorithm=settings.algorithm)
    return {"Authorization": f"Bearer {token}"}


def test_health_identifies_ia_service():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "kolia-ia-service",
    }


def test_analisar_requires_bearer_token():
    response = client.post(
        "/analisar",
        json={
            "meeting_id": "55555555-5555-5555-5555-555555555555",
            "title": "Reunião",
            "transcription": "Conteúdo qualquer.",
        },
    )

    assert response.status_code == 401


def test_analisar_rejects_invalid_token():
    response = client.post(
        "/analisar",
        json={
            "meeting_id": "55555555-5555-5555-5555-555555555555",
            "title": "Reunião",
            "transcription": "Conteúdo qualquer.",
        },
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401


def test_analisar_rejects_invalid_payload_before_database_access():
    response = client.post(
        "/analisar",
        json={
            "meeting_id": "not-a-uuid",
            "title": "",
            "transcription": "",
        },
        headers=_auth_header(),
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
            headers=_auth_header(),
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
            headers=_auth_header(),
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
            f"/analises/{analysis_id}/evidencias",
            params={"top_k": 2},
            headers=_auth_header(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["categories"]["budget"][0]["chunk_index"] == 3


class ChatSession:
    """Sessão suficiente para o endpoint de chat, que agora lê e grava conversa.

    `object()` bastava enquanto o endpoint só repassava para o serviço; desde
    que a conversa passou a ser guardada, ele consulta o banco antes de
    responder, e uma sessão sem `execute` viraria 503 mascarando o erro real.
    """

    def __init__(self, stored=(), results=None):
        # Cada `execute` devolve o próximo item de `results`; quando acabam, `stored`.
        self._stored = list(stored)
        self._results = [list(rows) for rows in results] if results else []
        self.saved = []

    def execute(self, _statement):
        rows = self._results.pop(0) if self._results else self._stored

        class _Result:
            def scalars(self):
                return iter(rows)

        return _Result()

    def add_all(self, messages):
        self.saved.extend(messages)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_chat_returns_grounded_answer_with_server_citations(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: ChatSession()
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
    app.dependency_overrides[get_db] = lambda: ChatSession()
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
    app.dependency_overrides[get_db] = lambda: ChatSession()
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
    app.dependency_overrides[get_db] = lambda: ChatSession()
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
    app.dependency_overrides[get_db] = lambda: ChatSession()
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


CONVERSATION_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _stored_turns():
    return [
        SimpleNamespace(role="user", content="Quantas lojas o cliente tem?",
                        grounded=None, fallback_reason=None,
                        created_at=datetime(2026, 9, 9, 12, 0)),
        SimpleNamespace(role="assistant", content="15 lojas.",
                        grounded=True, fallback_reason=None,
                        created_at=datetime(2026, 9, 9, 12, 0, 5)),
    ]


def _conversation(conversation_id=CONVERSATION_ID, title="Quantas lojas o cliente tem?"):
    return SimpleNamespace(id=conversation_id, title=title,
                           created_at=datetime(2026, 9, 9, 12, 0),
                           updated_at=datetime(2026, 9, 9, 12, 0, 5))


def _answer_recording(visto):
    def fake_answer(_db, current_id, payload):
        visto["history"] = [(m.role, m.content) for m in payload.history]
        return {
            "analysis_id": current_id,
            "answer": "São Paulo.",
            "citations": [],
            "grounded": True,
            "fallback_reason": None,
        }
    return fake_answer


INVENTED_HISTORY = [
    {"role": "user", "content": "histórico que o cliente inventou"},
    {"role": "assistant", "content": "resposta que o cliente inventou"},
]


def test_chat_continues_the_chosen_conversation_with_its_stored_history(monkeypatch):
    """A conversa guardada manda, não o que o cliente reenvia.

    Antes disto o histórico vivia só no payload do navegador: recarregar a
    página apagava a conversa, e duas abas na mesma reunião divergiam.
    """
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    sessao = ChatSession(results=[[_conversation()], _stored_turns()])
    app.dependency_overrides[get_db] = lambda: sessao
    visto = {}
    monkeypatch.setattr(main, "answer_analysis_question", _answer_recording(visto))
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat",
            json={"question": "Em que estado?", "conversation_id": str(CONVERSATION_ID),
                  "history": INVENTED_HISTORY},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(CONVERSATION_ID)
    assert visto["history"] == [
        ("user", "Quantas lojas o cliente tem?"),
        ("assistant", "15 lojas."),
    ], "o histórico do banco deve substituir o que o cliente mandou"
    mensagens = [item for item in sessao.saved if hasattr(item, "role")]
    assert [(m.role, m.content, m.conversation_id) for m in mensagens] == [
        ("user", "Em que estado?", CONVERSATION_ID),
        ("assistant", "São Paulo.", CONVERSATION_ID),
    ]


def test_a_question_without_a_conversation_starts_a_new_one(monkeypatch):
    """O botão "Nova conversa" só limpava a tela: a pergunta seguinte caía na
    conversa guardada da reunião. Sem `conversation_id`, agora nasce outra, sem
    passado, e as anteriores continuam guardadas à parte."""
    from src.app.models.analysis import ChatConversation

    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    sessao = ChatSession(stored=_stored_turns())
    app.dependency_overrides[get_db] = lambda: sessao
    visto = {}
    monkeypatch.setattr(main, "answer_analysis_question", _answer_recording(visto))
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat",
            json={"question": "Qual o prazo da implantação?", "history": INVENTED_HISTORY},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert visto["history"] == []
    conversas = [item for item in sessao.saved if isinstance(item, ChatConversation)]
    assert len(conversas) == 1
    assert conversas[0].analysis_id == analysis_id
    assert conversas[0].title == "Qual o prazo da implantação?"
    assert response.json()["conversation_id"] == str(conversas[0].id)
    mensagens = [item for item in sessao.saved if hasattr(item, "role")]
    assert {m.conversation_id for m in mensagens} == {conversas[0].id}


def test_a_conversation_that_is_not_of_this_meeting_is_404(monkeypatch):
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[]])
    monkeypatch.setattr(
        main, "answer_analysis_question",
        lambda *_args: (_ for _ in ()).throw(AssertionError("não deveria responder")),
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat",
            json={"question": "Qual produto?", "conversation_id": str(CONVERSATION_ID)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversa não encontrada nesta reunião."


def test_conversations_endpoint_lists_the_meeting_conversations():
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    outra = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[
        _conversation(outra, "Quais os riscos?"), _conversation(),
    ]])
    try:
        response = client.get(f"/analises/{analysis_id}/conversas")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [(c["id"], c["title"]) for c in response.json()["conversations"]] == [
        (str(outra), "Quais os riscos?"),
        (str(CONVERSATION_ID), "Quantas lojas o cliente tem?"),
    ]


def test_conversation_endpoint_returns_that_conversation_or_404():
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[_conversation()], _stored_turns()])
    try:
        response = client.get(f"/analises/{analysis_id}/conversas/{CONVERSATION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(CONVERSATION_ID)
    assert [m["content"] for m in response.json()["messages"]] == [
        "Quantas lojas o cliente tem?", "15 lojas."]

    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[]])
    try:
        missing = client.get(f"/analises/{analysis_id}/conversas/{CONVERSATION_ID}")
    finally:
        app.dependency_overrides.clear()
    assert missing.status_code == 404


def test_chat_answers_even_when_saving_the_turn_fails(monkeypatch):
    """O usuário já tem a resposta; perder o registro não pode virar 503."""
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    class SessaoQuebrada(ChatSession):
        def add_all(self, _messages):
            raise RuntimeError("banco fora do ar")

    app.dependency_overrides[get_db] = lambda: SessaoQuebrada()
    monkeypatch.setattr(
        main,
        "answer_analysis_question",
        lambda _db, current_id, _payload: {
            "analysis_id": current_id,
            "answer": "São Paulo.",
            "citations": [],
            "grounded": True,
            "fallback_reason": None,
        },
    )
    try:
        response = client.post(
            f"/analises/{analysis_id}/chat", json={"question": "Em que estado?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "São Paulo."


def test_chat_history_endpoint_returns_the_latest_conversation():
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[_conversation()], _stored_turns()])
    try:
        response = client.get(f"/analises/{analysis_id}/chat")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["conversation_id"] == str(CONVERSATION_ID)
    assert [m["content"] for m in corpo["messages"]] == ["Quantas lojas o cliente tem?", "15 lojas."]
    assert corpo["messages"][1]["grounded"] is True


def test_chat_history_endpoint_is_empty_for_a_meeting_without_conversations():
    analysis_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    app.dependency_overrides[get_db] = lambda: ChatSession(results=[[]])
    try:
        response = client.get(f"/analises/{analysis_id}/chat")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"analysis_id": str(analysis_id), "conversation_id": None, "messages": []}
