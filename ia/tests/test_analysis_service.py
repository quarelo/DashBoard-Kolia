from uuid import UUID, uuid4

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services import analysis_service


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, value):
        if isinstance(value, MeetingAnalysis) and value.id is None:
            value.id = uuid4()

    def merge(self, value):
        return value


def test_analyze_meeting_persists_real_ollama_results(monkeypatch):
    chunk_summary = {
        "resumo_chunk": "Cliente relatou dificuldade com ERP e marcou reunião técnica.",
        "temas_discutidos": ["Integração ERP"],
        "problemas_identificados": ["Dificuldade na integração com ERP"],
        "decisoes_tomadas": ["Marcar reunião técnica sexta-feira"],
        "duvidas_em_aberto": [],
        "oportunidades_insights": [],
        "evidencias_importantes": [],
        "metricas_negocio": {},
        "acoes_recomendadas": ["Realizar reunião técnica"],
    }
    embedding = [0.25] * 768

    monkeypatch.setattr(
        analysis_service, "generate_chunk_summary", lambda _text: chunk_summary
    )
    monkeypatch.setattr(
        analysis_service, "generate_embedding", lambda _text: embedding
    )
    monkeypatch.setattr(
        analysis_service,
        "consolidate_summaries",
        lambda _summaries: (_ for _ in ()).throw(
            AssertionError("um único chunk não deve ser reinterpretado")
        ),
    )
    session = FakeSession()
    payload = AnalyzeRequest(
        meeting_id=UUID("11111111-1111-1111-1111-111111111111"),
        user_id=None,
        title="Reunião ERP",
        transcription=(
            "Cliente comentou dificuldade na integração com ERP. "
            "Foi decidido marcar uma reunião técnica sexta-feira."
        ),
    )

    result = analysis_service.analyze_meeting(session, payload)

    stored_chunk = next(value for value in session.added if isinstance(value, MeetingChunk))
    assert stored_chunk.chunk_summary == chunk_summary
    assert stored_chunk.embedding == embedding
    assert result.final_summary["resumo_geral"] == chunk_summary["resumo_chunk"]
    assert result.final_summary["decisoes_tomadas"] == [
        "Marcar reunião técnica sexta-feira"
    ]
    assert result.final_summary["problemas_identificados"] == [
        "Dificuldade na integração com ERP"
    ]
    assert result.final_summary["acoes_recomendadas"] == [
        "Realizar reunião técnica"
    ]
    assert result.total_tokens == 18
    assert result.status == "DONE"


def test_failed_analysis_keeps_counts_and_useful_error(monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "generate_chunk_summary",
        lambda _text: (_ for _ in ()).throw(RuntimeError("JSON inválido")),
    )
    session = FakeSession()
    payload = AnalyzeRequest(
        meeting_id=UUID("55555555-5555-5555-5555-555555555555"),
        user_id=None,
        title="Reunião com falha",
        transcription="Cliente relatou erro na integração.",
    )

    result = analysis_service.analyze_meeting(session, payload)

    assert result.status == "FAILED"
    assert result.total_tokens == 6
    assert result.total_chunks == 1
    assert result.error_message == "JSON inválido"
