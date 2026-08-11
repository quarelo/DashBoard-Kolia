import logging
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services.chunk_service import clean_chunk_text, sanitize_transcription
from src.app.services.llm_service import (
    consolidate_summaries,
    generate_chunk_summary,
    generate_embedding,
)
from src.app.services.token_service import count_tokens, split_text_by_tokens

logger = logging.getLogger("uvicorn.error")


def build_single_chunk_final_summary(summary: dict) -> dict:
    themes = summary.get("temas_discutidos", [])
    return {
        "resumo_geral": summary.get("resumo_chunk", ""),
        "temas_agrupados": [
            {"tema": theme, "pontos": [theme]} for theme in themes
        ],
        "problemas_identificados": summary.get("problemas_identificados", []),
        "decisoes_tomadas": summary.get("decisoes_tomadas", []),
        "duvidas_em_aberto": summary.get("duvidas_em_aberto", []),
        "oportunidades_insights": summary.get("oportunidades_insights", []),
        "evidencias_importantes": summary.get("evidencias_importantes", []),
        "metricas_negocio": summary.get("metricas_negocio", {}),
        "acoes_recomendadas": summary.get("acoes_recomendadas", []),
    }


def prepare_analysis(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    transcription = sanitize_transcription(payload.transcription)
    chunks = split_text_by_tokens(
        transcription,
        settings.max_tokens_per_chunk,
        settings.overlap_tokens,
    )
    analysis = MeetingAnalysis(external_meeting_id=payload.meeting_id, external_user_id=payload.user_id, title=payload.title, status="PROCESSING")
    analysis.total_tokens = count_tokens(transcription)
    analysis.total_chunks = len(chunks)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    for index, content in enumerate(chunks, start=1):
        db.add(
            MeetingChunk(
                analysis_id=analysis.id,
                external_meeting_id=payload.meeting_id,
                external_user_id=payload.user_id,
                chunk_index=index,
                token_count=count_tokens(content),
                content=content,
                clean_content=clean_chunk_text(content),
            )
        )
    db.commit()
    db.refresh(analysis)
    return analysis


def _analysis_chunks(db: Session, analysis_id: UUID) -> list[MeetingChunk]:
    statement = (
        select(MeetingChunk)
        .where(MeetingChunk.analysis_id == analysis_id)
        .order_by(MeetingChunk.chunk_index.asc())
    )
    return list(db.execute(statement).scalars().all())


def process_analysis_summaries(
    db: Session, analysis_id: UUID
) -> MeetingAnalysis:
    analysis = db.get(MeetingAnalysis, analysis_id)
    if analysis is None:
        raise ValueError(f"Análise não encontrada: {analysis_id}")

    try:
        analysis.status = "ANALYZING"
        analysis.error_message = None
        db.commit()
        db.refresh(analysis)

        chunks = _analysis_chunks(db, analysis_id)
        summaries = []
        for chunk in chunks:
            if chunk.chunk_summary is None:
                started_at = perf_counter()
                chunk.chunk_summary = generate_chunk_summary(
                    chunk.clean_content or chunk.content
                )
                logger.info(
                    "analysis_id=%s chunk=%d summary_seconds=%.3f",
                    analysis.id,
                    chunk.chunk_index,
                    perf_counter() - started_at,
                )
                db.commit()
            summaries.append(chunk.chunk_summary)

        if len(summaries) == 1:
            analysis.final_summary = build_single_chunk_final_summary(summaries[0])
            logger.info("analysis_id=%s single_chunk_consolidation=skipped", analysis.id)
        else:
            started_at = perf_counter()
            analysis.final_summary = consolidate_summaries(summaries)
            logger.info("analysis_id=%s consolidation_seconds=%.3f", analysis.id, perf_counter() - started_at)
        analysis.status = "DASHBOARD_READY"
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as error:
        logger.exception("analysis_id=%s failed", analysis.id)
        db.rollback()
        analysis = db.merge(analysis)
        analysis.status = "FAILED_ANALYSIS"
        analysis.error_message = str(error)
        db.commit()
        db.refresh(analysis)
        return analysis


def process_analysis_embeddings(
    db: Session, analysis_id: UUID
) -> MeetingAnalysis:
    analysis = db.get(MeetingAnalysis, analysis_id)
    if analysis is None:
        raise ValueError(f"Análise não encontrada: {analysis_id}")
    if analysis.final_summary is None:
        raise ValueError("A análise precisa estar pronta antes dos embeddings.")

    try:
        analysis.status = "EMBEDDING"
        analysis.error_message = None
        db.commit()
        db.refresh(analysis)

        for chunk in _analysis_chunks(db, analysis.id):
            if chunk.embedding is not None:
                continue
            started_at = perf_counter()
            chunk.embedding = generate_embedding(chunk.clean_content or chunk.content)
            logger.info(
                "analysis_id=%s chunk=%d embedding_seconds=%.3f",
                analysis.id,
                chunk.chunk_index,
                perf_counter() - started_at,
            )
            db.commit()

        analysis.status = "DONE"
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as error:
        logger.exception("analysis_id=%s embedding_failed", analysis.id)
        db.rollback()
        analysis = db.merge(analysis)
        analysis.status = "DASHBOARD_READY_WITH_EMBEDDING_ERROR"
        analysis.error_message = str(error)
        db.commit()
        db.refresh(analysis)
        return analysis


def analyze_meeting(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    analysis = prepare_analysis(db, payload)
    analysis = process_analysis_summaries(db, analysis.id)
    if analysis.status != "DASHBOARD_READY":
        # Compatibility for the existing synchronous endpoint.
        analysis.status = "FAILED"
        db.commit()
        db.refresh(analysis)
        return analysis

    analysis = process_analysis_embeddings(db, analysis.id)
    if analysis.status == "DASHBOARD_READY_WITH_EMBEDDING_ERROR":
        analysis.status = "FAILED"
        db.commit()
        db.refresh(analysis)
    return analysis
