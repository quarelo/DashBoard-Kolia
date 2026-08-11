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

    def get(self, model, value_id):
        return next(
            (
                value
                for value in self.added
                if isinstance(value, model) and value.id == value_id
            ),
            None,
        )

    def execute(self, _statement):
        chunks = sorted(
            (
                value
                for value in self.added
                if isinstance(value, MeetingChunk)
            ),
            key=lambda chunk: chunk.chunk_index,
        )
        return FakeResult(chunks)


class FakeResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


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


def test_prepare_analysis_persists_chunks_without_calling_ollama(monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "generate_chunk_summary",
        lambda _text: (_ for _ in ()).throw(
            AssertionError("preparation must not call Ollama")
        ),
    )
    session = FakeSession()
    payload = AnalyzeRequest(
        meeting_id=UUID("77777777-7777-7777-7777-777777777777"),
        user_id=None,
        title="Reunião preparada",
        transcription="Primeiro fato. Segundo fato.",
    )

    result = analysis_service.prepare_analysis(session, payload)

    stored_chunks = [
        value for value in session.added if isinstance(value, MeetingChunk)
    ]
    assert result.status == "PROCESSING"
    assert len(stored_chunks) == result.total_chunks == 1
    assert stored_chunks[0].chunk_summary is None
    assert stored_chunks[0].embedding is None


def test_resume_summaries_skips_completed_chunks(monkeypatch):
    analysis_id = uuid4()
    analysis = MeetingAnalysis(
        id=analysis_id,
        external_meeting_id=uuid4(),
        title="Retomada",
        status="ANALYZING",
        total_tokens=4,
        total_chunks=2,
    )
    complete = {
        "resumo_chunk": "já pronto",
        "temas_discutidos": [],
        "problemas_identificados": [],
        "decisoes_tomadas": [],
        "duvidas_em_aberto": [],
        "oportunidades_insights": [],
        "evidencias_importantes": [],
        "metricas_negocio": {},
        "acoes_recomendadas": [],
    }
    pending = MeetingChunk(
        analysis_id=analysis_id,
        external_meeting_id=analysis.external_meeting_id,
        chunk_index=2,
        token_count=2,
        content="chunk dois",
        clean_content="chunk dois",
    )
    session = FakeSession()
    session.added.extend(
        [
            analysis,
            MeetingChunk(
                analysis_id=analysis_id,
                external_meeting_id=analysis.external_meeting_id,
                chunk_index=1,
                token_count=2,
                content="chunk um",
                clean_content="chunk um",
                chunk_summary=complete,
            ),
            pending,
        ]
    )
    calls = []
    monkeypatch.setattr(
        analysis_service,
        "generate_chunk_summary",
        lambda text: calls.append(text) or {**complete, "resumo_chunk": text},
    )
    monkeypatch.setattr(
        analysis_service,
        "consolidate_summaries",
        lambda summaries: {"resumo_geral": ", ".join(s["resumo_chunk"] for s in summaries)},
    )

    result = analysis_service.process_analysis_summaries(session, analysis_id)

    assert calls == ["chunk dois"]
    assert pending.chunk_summary["resumo_chunk"] == "chunk dois"
    assert result.status == "DASHBOARD_READY"
    assert result.final_summary == {"resumo_geral": "já pronto, chunk dois"}


def test_resume_embeddings_skips_existing_vectors(monkeypatch):
    analysis_id = uuid4()
    analysis = MeetingAnalysis(
        id=analysis_id,
        external_meeting_id=uuid4(),
        title="Embeddings",
        status="DASHBOARD_READY",
        total_tokens=4,
        total_chunks=2,
        final_summary={"resumo_geral": "pronto"},
    )
    first = MeetingChunk(
        analysis_id=analysis_id,
        external_meeting_id=analysis.external_meeting_id,
        chunk_index=1,
        token_count=2,
        content="chunk um",
        clean_content="chunk um",
        embedding=[0.1] * 768,
    )
    second = MeetingChunk(
        analysis_id=analysis_id,
        external_meeting_id=analysis.external_meeting_id,
        chunk_index=2,
        token_count=2,
        content="chunk dois",
        clean_content="chunk dois",
    )
    session = FakeSession()
    session.added.extend([analysis, first, second])
    calls = []
    monkeypatch.setattr(
        analysis_service,
        "generate_embedding",
        lambda text: calls.append(text) or [0.2] * 768,
    )

    result = analysis_service.process_analysis_embeddings(session, analysis_id)

    assert calls == ["chunk dois"]
    assert second.embedding == [0.2] * 768
    assert result.status == "DONE"
    assert result.final_summary == {"resumo_geral": "pronto"}


def test_embedding_failure_preserves_dashboard(monkeypatch):
    analysis_id = uuid4()
    analysis = MeetingAnalysis(
        id=analysis_id,
        external_meeting_id=uuid4(),
        title="Falha de embedding",
        status="DASHBOARD_READY",
        total_tokens=2,
        total_chunks=1,
        final_summary={"resumo_geral": "continua disponível"},
    )
    session = FakeSession()
    session.added.extend(
        [
            analysis,
            MeetingChunk(
                analysis_id=analysis_id,
                external_meeting_id=analysis.external_meeting_id,
                chunk_index=1,
                token_count=2,
                content="conteúdo",
                clean_content="conteúdo",
            ),
        ]
    )
    monkeypatch.setattr(
        analysis_service,
        "generate_embedding",
        lambda _text: (_ for _ in ()).throw(RuntimeError("embedding indisponível")),
    )

    result = analysis_service.process_analysis_embeddings(session, analysis_id)

    assert result.status == "DASHBOARD_READY_WITH_EMBEDDING_ERROR"
    assert result.final_summary == {"resumo_geral": "continua disponível"}
    assert result.error_message == "embedding indisponível"
