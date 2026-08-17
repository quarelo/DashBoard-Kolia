from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from threading import Barrier, Lock
from types import SimpleNamespace

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services import analysis_service
from src.app.core.config import settings


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


def test_analysis_progress_reports_partial_coverage_and_eta():
    started = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    analysis = MeetingAnalysis(
        external_meeting_id=uuid4(), title="Progresso", total_chunks=8,
        created_at=started,
    )
    chunks = [
        SimpleNamespace(chunk_summary={"pontos_chave": ["fato"]}),
        SimpleNamespace(chunk_summary={"pontos_chave": ["fato"]}),
        SimpleNamespace(chunk_summary=None),
    ]

    progress = analysis_service.build_analysis_progress(
        analysis, chunks, now=started + timedelta(seconds=40)
    )

    assert {
        key: progress[key]
        for key in (
            "processed_chunks", "total_chunks", "progress_percent",
            "is_partial", "estimated_seconds_remaining",
        )
    } == {
        "processed_chunks": 2,
        "total_chunks": 8,
        "progress_percent": 25.0,
        "is_partial": True,
        "estimated_seconds_remaining": 120,
    }


def test_analysis_progress_handles_not_started_and_complete_states():
    analysis = MeetingAnalysis(
        external_meeting_id=uuid4(), title="Progresso", total_chunks=2
    )

    waiting = analysis_service.build_analysis_progress(
        analysis, [SimpleNamespace(chunk_summary=None)]
    )
    complete = analysis_service.build_analysis_progress(
        analysis,
        [SimpleNamespace(chunk_summary={}), SimpleNamespace(chunk_summary={})],
    )

    assert waiting["estimated_seconds_remaining"] is None
    assert waiting["progress_percent"] == 0.0
    assert waiting["is_partial"] is True
    assert complete["estimated_seconds_remaining"] == 0
    assert complete["progress_percent"] == 100.0
    assert complete["is_partial"] is False


def test_analysis_progress_uses_only_current_attempt_for_resumed_eta():
    created = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
    attempt_started = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    analysis = MeetingAnalysis(
        external_meeting_id=uuid4(),
        title="Retomada",
        total_chunks=8,
        created_at=created,
        summary_attempt_started_at=attempt_started,
        summary_attempt_started_chunks=2,
    )
    chunks = [
        SimpleNamespace(chunk_summary={}),
        SimpleNamespace(chunk_summary={}),
        SimpleNamespace(chunk_summary={}),
        SimpleNamespace(chunk_summary={}),
    ]

    progress = analysis_service.build_analysis_progress(
        analysis, chunks, now=attempt_started + timedelta(seconds=40)
    )

    assert progress["estimated_seconds_remaining"] == 80


def test_analysis_progress_separates_summary_and_embedding_stages():
    analysis = MeetingAnalysis(
        external_meeting_id=uuid4(),
        title="Progresso independente",
        status="EMBEDDING",
        total_chunks=4,
        summary_stage="COMPLETE",
        summary_is_final=True,
    )
    chunks = [
        SimpleNamespace(chunk_summary={}, embedding=[0.1]),
        SimpleNamespace(chunk_summary={}, embedding=[0.2]),
        SimpleNamespace(chunk_summary={}, embedding=None),
        SimpleNamespace(chunk_summary={}, embedding=None),
    ]

    progress = analysis_service.build_analysis_progress(analysis, chunks)

    assert progress["summary_stage"] == "COMPLETE"
    assert progress["summary_is_final"] is True
    assert progress["summary_progress_percent"] == 100.0
    assert progress["embedding_progress_percent"] == 50.0
    assert progress["summary_estimated_seconds_remaining"] == 0
    assert progress["progress_percent"] == 100.0


def test_preliminary_summary_keeps_worst_case_critical_facts():
    transcription = (
        "[LOCUTOR 1]: Vamos fazer o CRM para 25 pessoas. "
        "[LOCUTOR 2]: Precisamos decidir entre 20 ou 40 licenças. "
        "[LOCUTOR 1]: Na segunda-feira vamos enviar o plano. "
        "[LOCUTOR 2]: O levantamento apontou a substituição de 27 máquinas. "
        "[LOCUTOR 1]: Em março ou abril vamos refazer o estudo de cloud."
    )

    result = analysis_service.build_preliminary_summary(transcription)
    serialized = str(result).casefold()

    assert set(result) == {
        "resumo_geral", "temas_agrupados", "problemas_identificados",
        "decisoes_tomadas", "duvidas_em_aberto", "oportunidades_insights",
        "evidencias_importantes", "metricas_negocio", "acoes_recomendadas",
    }
    for expected in ("25 pessoas", "20 ou 40", "segunda-feira", "27 máquinas", "março ou abril"):
        assert expected in serialized


def test_preliminary_summary_parses_tokenizer_spaced_speaker_tags():
    result = analysis_service.build_preliminary_summary(
        "[ L67 ] : Precisamos substituir 27 máquinas. "
        "[ L73 ] : Vamos revisar cloud em março ou abril."
    )

    assert "27 máquinas" in result["evidencias_importantes"][0]
    assert all(len(item) < 100 for item in result["evidencias_importantes"])


def test_preliminary_summary_splits_long_turn_before_critical_fact():
    result = analysis_service.build_preliminary_summary(
        "[ L67 ] : " + ("Contexto sem valor. " * 30) +
        "O levantamento apontou 27 máquinas."
    )

    assert any(
        "27 máquinas" in item for item in result["evidencias_importantes"]
    )


def test_compact_summary_bounds_malformed_long_model_fact():
    result = analysis_service.build_compact_final_summary([{
        "pontos_chave": ["AÇÃO: " + ("texto muito longo " * 100)]
    }])

    assert len(result["acoes_recomendadas"][0]) <= 321
    assert result["acoes_recomendadas"][0].endswith("…")


def test_compact_summary_metrics_keep_late_transcript_facts():
    facts = [f"VALOR: métrica {index}" for index in range(30)]
    facts += ["VALOR: substituição de 27 máquinas"]
    result = analysis_service.build_compact_final_summary([{
        "pontos_chave": facts
    }])

    assert "27 máquinas" in result["metricas_negocio"]["valores"]


def test_model_summary_is_enriched_with_deterministic_evidence():
    result = analysis_service.merge_deterministic_evidence(
        {"resumo_chunk": "Resumo", "pontos_chave": ["INSIGHT: ponto do modelo"]},
        "[ L67 ] : O levantamento apontou 27 máquinas.",
    )

    assert "INSIGHT: ponto do modelo" in result["pontos_chave"]
    assert any("27 máquinas" in point for point in result["pontos_chave"])


def test_prepare_analysis_persists_preliminary_summary():
    session = FakeSession()
    payload = AnalyzeRequest(
        meeting_id=uuid4(),
        title="Resumo imediato",
        transcription="[LOCUTOR 1]: Foi decidido enviar a proposta de R$ 500 amanhã.",
    )

    result = analysis_service.prepare_analysis(session, payload)

    assert "R$ 500" in str(result.final_summary)
    assert result.summary_stage == "PRELIMINARY"
    assert result.summary_is_final is False


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
    for key, value in chunk_summary.items():
        assert stored_chunk.chunk_summary[key] == value
    assert any(
        "sexta-feira" in point
        for point in stored_chunk.chunk_summary["pontos_chave"]
    )
    assert stored_chunk.embedding == embedding
    assert "reunião técnica sexta-feira" in result.final_summary["resumo_geral"]
    assert "dificuldade na integração com ERP" in result.final_summary["resumo_geral"]
    assert "Marcar reunião técnica sexta-feira" in result.final_summary["decisoes_tomadas"]
    assert "Dificuldade na integração com ERP" in result.final_summary["problemas_identificados"]
    assert "Realizar reunião técnica" in result.final_summary["acoes_recomendadas"]
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


def test_prepare_analysis_splits_compacted_transcription(monkeypatch):
    monkeypatch.setattr(settings, "max_tokens_per_chunk", 8)
    monkeypatch.setattr(settings, "overlap_tokens", 0)
    session = FakeSession()
    transcription = (
        "[LOCUTOR 1]: Boa tarde.\n"
        "[LOCUTOR 2]: O contrato será assinado sexta-feira.\n"
        "[LOCUTOR 2]: O valor é R$ 500."
    )
    payload = AnalyzeRequest(
        meeting_id=uuid4(), user_id=None, title="Compactação", transcription=transcription
    )

    result = analysis_service.prepare_analysis(session, payload)

    stored = [value for value in session.added if isinstance(value, MeetingChunk)]
    assert result.total_tokens == analysis_service.count_tokens(
        analysis_service.sanitize_transcription(transcription)
    )
    assert "Boa tarde" not in " ".join(chunk.content for chunk in stored)
    assert "L2" in " ".join(chunk.clean_content for chunk in stored)


def test_prepare_analysis_uses_full_cleaned_transcription(monkeypatch):
    calls = []
    monkeypatch.setattr(
        analysis_service,
        "clean_transcription",
        lambda text: calls.append(text) or "conteúdo completo limpo",
    )
    session = FakeSession()
    payload = AnalyzeRequest(
        meeting_id=uuid4(), user_id=None, title="Rápida", transcription="conteúdo original"
    )

    analysis_service.prepare_analysis(session, payload)

    chunk = next(value for value in session.added if isinstance(value, MeetingChunk))
    assert calls == ["conteúdo original"]
    assert chunk.content == "conteúdo completo limpo"


def test_pending_summaries_overlap_when_concurrency_is_two(monkeypatch):
    barrier = Barrier(2)
    lock = Lock()
    active = 0
    peak_active = 0

    def generate(text):
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        barrier.wait(timeout=2)
        with lock:
            active -= 1
        return {"resumo_chunk": text}

    monkeypatch.setattr(analysis_service, "generate_chunk_summary", generate)
    chunks = [
        SimpleNamespace(chunk_index=1, clean_content="um", content="um"),
        SimpleNamespace(chunk_index=2, clean_content="dois", content="dois"),
    ]

    results = dict(analysis_service.iter_pending_summaries(chunks, concurrency=2))

    assert peak_active == 2
    assert results[1]["resumo_chunk"] == "um"
    assert results[2]["resumo_chunk"] == "dois"


def test_pending_summaries_rejects_concurrency_above_two():
    try:
        list(analysis_service.iter_pending_summaries([], concurrency=3))
    except ValueError as error:
        assert "1 ou 2" in str(error)
    else:
        raise AssertionError("concorrência maior que dois deve ser rejeitada")


def test_single_compact_chunk_preserves_key_points_as_evidence():
    summary = {
        "pontos_chave": [
            "DECISÃO: contrato será assinado",
            "PRAZO: sexta-feira",
        ]
    }

    result = analysis_service.build_single_chunk_final_summary(summary)

    assert result["evidencias_importantes"] == summary["pontos_chave"]


def test_compact_final_summary_routes_prefixed_facts_without_llm():
    summaries = [
        {"pontos_chave": [
            "DECISÃO: aprovar contrato",
            "AÇÃO: enviar proposta",
            "VALOR: R$ 500",
        ]},
        {"pontos_chave": [
            "PROBLEMA: integração indisponível",
            "DÚVIDA: qual é o prazo?",
            "PRAZO: sexta-feira",
        ]},
    ]

    result = analysis_service.build_compact_final_summary(summaries)

    assert result["decisoes_tomadas"] == ["aprovar contrato"]
    assert result["acoes_recomendadas"] == ["enviar proposta"]
    assert result["problemas_identificados"] == ["integração indisponível"]
    assert result["duvidas_em_aberto"] == ["qual é o prazo?"]
    assert result["metricas_negocio"] == {
        "valores": "R$ 500",
        "prazos": "sexta-feira",
    }


def test_compact_final_summary_preserves_unprefixed_model_facts():
    summaries = [{"pontos_chave": ["CRM automatiza a força de vendas."]}]

    result = analysis_service.build_compact_final_summary(summaries)

    assert result["resumo_geral"] == "CRM automatiza a força de vendas."
    assert result["evidencias_importantes"] == [
        "CRM automatiza a força de vendas."
    ]


def test_compact_final_summary_prioritizes_late_quantified_facts():
    summaries = [
        {"pontos_chave": [
            "AÇÃO: conversar sobre o projeto",
            "AÇÃO: avaliar opções",
            "AÇÃO: revisar o cenário",
        ]},
        {"pontos_chave": [
            "AÇÃO: montar o plano na segunda-feira",
            "VALOR: 40 licenças para força de vendas",
            "VALOR: 25 licenças para CRM",
        ]},
    ]

    result = analysis_service.build_compact_final_summary(summaries)

    assert "montar o plano na segunda-feira" in result["acoes_recomendadas"]
    assert result["metricas_negocio"]["valores"] == (
        "40 licenças para força de vendas; 25 licenças para CRM"
    )


def test_compact_final_summary_discards_vague_values_and_deadlines():
    summaries = [{"pontos_chave": [
        "VALOR: investimento em estudo",
        "VALOR: R$ 500 mil em pedidos",
        "PRAZO: verificar opções",
        "PRAZO: revisar o PD4000",
        "PRAZO: concluir em X semanas",
        "PRAZO: configurar rotas semanais",
        "PRAZO: entregar na segunda-feira",
    ]}]

    result = analysis_service.build_compact_final_summary(summaries)

    assert result["metricas_negocio"] == {
        "valores": "R$ 500 mil em pedidos",
        "prazos": "entregar na segunda-feira",
    }


def test_resume_summaries_skips_completed_chunks(monkeypatch):
    monkeypatch.setattr(settings, "fast_deterministic_consolidation", False)
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
    monkeypatch.setattr(
        analysis_service, "complete_missing_fields", lambda summary, _chunks: summary
    )

    result = analysis_service.process_analysis_summaries(session, analysis_id)

    assert calls == ["chunk dois"]
    assert pending.chunk_summary["resumo_chunk"] == "chunk dois"
    assert result.status == "DASHBOARD_READY"
    assert result.summary_attempt_started_at is not None
    assert result.summary_attempt_started_chunks == 1
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
