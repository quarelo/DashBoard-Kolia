import logging
from time import perf_counter

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


def analyze_meeting(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    analysis = MeetingAnalysis(external_meeting_id=payload.meeting_id, external_user_id=payload.user_id, title=payload.title, status="PROCESSING")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    try:
        transcription = sanitize_transcription(payload.transcription)
        chunks = split_text_by_tokens(transcription, settings.max_tokens_per_chunk, settings.overlap_tokens)
        analysis.total_tokens = count_tokens(transcription)
        analysis.total_chunks = len(chunks)
        db.commit()
        db.refresh(analysis)
        summaries = []
        for index, content in enumerate(chunks, start=1):
            clean_content = clean_chunk_text(content)
            started_at = perf_counter()
            summary = generate_chunk_summary(clean_content)
            logger.info("analysis_id=%s chunk=%d summary_seconds=%.3f", analysis.id, index, perf_counter() - started_at)
            started_at = perf_counter()
            embedding = generate_embedding(clean_content)
            logger.info("analysis_id=%s chunk=%d embedding_seconds=%.3f", analysis.id, index, perf_counter() - started_at)
            db.add(MeetingChunk(analysis_id=analysis.id, external_meeting_id=payload.meeting_id, external_user_id=payload.user_id, chunk_index=index, token_count=count_tokens(content), content=content, clean_content=clean_content, chunk_summary=summary, embedding=embedding))
            summaries.append(summary)
        if len(summaries) == 1:
            analysis.final_summary = build_single_chunk_final_summary(summaries[0])
            logger.info("analysis_id=%s single_chunk_consolidation=skipped", analysis.id)
        else:
            started_at = perf_counter()
            analysis.final_summary = consolidate_summaries(summaries)
            logger.info("analysis_id=%s consolidation_seconds=%.3f", analysis.id, perf_counter() - started_at)
        analysis.status = "DONE"
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as error:
        logger.exception("analysis_id=%s failed", analysis.id)
        db.rollback()
        analysis = db.merge(analysis)
        analysis.status = "FAILED"
        analysis.error_message = str(error)
        db.commit()
        db.refresh(analysis)
        return analysis
