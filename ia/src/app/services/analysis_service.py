import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services.chunk_service import (
    clean_chunk_text,
    clean_transcription,
    sanitize_transcription,
    rank_chunk_indices_for_partial,
)
from src.app.services.llm_service import (
    consolidate_summaries,
    complete_missing_fields,
    generate_chunk_summary,
    generate_embedding,
)
from src.app.services.token_service import count_tokens, split_text_by_tokens

logger = logging.getLogger("uvicorn.error")


_CRITICAL_FACT_PATTERN = re.compile(
    r"(?:R\$|\d|segunda|terça|quarta|quinta|sexta|sábado|domingo|"
    r"hoje|amanhã|prazo|até\b|não\b|nunca\b|sem\b)",
    re.IGNORECASE,
)
_QUANTIFIED_VALUE_PATTERN = re.compile(r"(?:R\$|\d)", re.IGNORECASE)
_BUSINESS_METRIC_PATTERN = re.compile(
    r"\b(?:licenças?|usuários?|pessoas?|máquinas?|equipamentos?|crm|cloud)\b",
    re.IGNORECASE,
)
_CALENDAR_METRIC_PATTERN = re.compile(
    r"\b(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro|segunda|terça|quarta|quinta|"
    r"sexta|sábado|domingo)\b",
    re.IGNORECASE,
)
_EXPLICIT_DEADLINE_PATTERN = re.compile(
    r"(?:segunda|terça|quarta|quinta|sexta|sábado|domingo|"
    r"janeiro|fevereiro|março|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro|"
    r"hoje|amanhã|(?:esta|próxima|próximo)\s+(?:semana|mês|ano)|"
    r"\d{1,2}[/-]\d{1,2}|"
    r"\d+\s*(?:dias?|horas?|semanas?|meses?|anos?))",
    re.IGNORECASE,
)
_PRELIMINARY_TURN_PATTERN = re.compile(
    r"\[\s*(?:L|LOCUTOR\s+)\s*\d+\s*\]\s*:\s*(.*?)"
    r"(?=\s*\[\s*(?:L|LOCUTOR\s+)\s*\d+\s*\]\s*:|$)",
    re.IGNORECASE,
)


def build_preliminary_summary(transcription: str) -> dict:
    """Build a fast evidence-first preview without invoking the LLM."""
    cleaned = sanitize_transcription(transcription)
    raw_turns = [
        match.group(1).strip()
        for match in _PRELIMINARY_TURN_PATTERN.finditer(cleaned)
        if match.group(1).strip()
    ] or ([cleaned] if cleaned else [])
    turns = [
        sentence.strip()
        for turn in raw_turns
        for sentence in re.split(r"(?<=[.!?])\s+", turn)
        if sentence.strip()
    ]

    signals = (
        (re.compile(r"(?:R\$|\d|%)", re.IGNORECASE), 120),
        (_EXPLICIT_DEADLINE_PATTERN, 110),
        (re.compile(r"\b(?:decid|defin|combin|aprov)\w*", re.IGNORECASE), 100),
        (re.compile(r"\b(?:enviar|entregar|fazer|agendar|substitu|refazer)\w*", re.IGNORECASE), 80),
        (re.compile(r"\b(?:problema|erro|risco|dúvida|pendente|não|sem)\w*", re.IGNORECASE), 70),
    )

    ranked = sorted(
        enumerate(turns),
        key=lambda item: (
            -sum(weight for pattern, weight in signals if pattern.search(item[1])),
            item[0],
        ),
    )
    selected = [text for _index, text in ranked[:30]]
    decisions = [
        text for text in selected
        if re.search(r"\b(?:decid|defin|combin|aprov)\w*", text, re.IGNORECASE)
    ][:8]
    actions = [
        text for text in selected
        if re.search(r"\b(?:enviar|entregar|fazer|agendar|substitu|refazer|vamos)\w*", text, re.IGNORECASE)
    ][:10]
    problems = [
        text for text in selected
        if re.search(r"\b(?:problema|erro|risco|dúvida|pendente|não|sem)\w*", text, re.IGNORECASE)
    ][:8]
    deadlines = [text for text in selected if _EXPLICIT_DEADLINE_PATTERN.search(text)][:8]
    quantified = [text for text in selected if _QUANTIFIED_VALUE_PATTERN.search(text)][:12]

    return {
        "resumo_geral": "; ".join(selected[:10]),
        "temas_agrupados": (
            [{"tema": "Prévia automática", "pontos": selected[:12]}]
            if selected else []
        ),
        "problemas_identificados": problems,
        "decisoes_tomadas": decisions,
        "duvidas_em_aberto": [],
        "oportunidades_insights": [],
        "evidencias_importantes": selected[:30],
        "metricas_negocio": {
            **({"valores": "; ".join(quantified)} if quantified else {}),
            **({"prazos": "; ".join(deadlines)} if deadlines else {}),
        },
        "acoes_recomendadas": actions,
    }


def build_deterministic_chunk_summary(text: str) -> dict:
    preview = build_preliminary_summary(text)
    points: list[str] = []
    categories = (
        ("DECISÃO", preview["decisoes_tomadas"]),
        ("AÇÃO", preview["acoes_recomendadas"]),
        ("PROBLEMA", preview["problemas_identificados"]),
        ("EVIDÊNCIA", preview["evidencias_importantes"]),
    )
    seen = set()
    for category, facts in categories:
        for fact in facts:
            normalized = fact.casefold()
            if normalized not in seen:
                points.append(f"{category}: {fact}")
                seen.add(normalized)
    metric_categories = (("VALOR", "valores"), ("PRAZO", "prazos"))
    for category, key in metric_categories:
        for fact in preview["metricas_negocio"].get(key, "").split("; "):
            fact = fact.strip()
            categorized = f"{category}: {fact}"
            if fact and categorized.casefold() not in {
                point.casefold() for point in points
            }:
                points.append(categorized)
    return {
        "resumo_chunk": preview["resumo_geral"],
        "temas_discutidos": ["Evidências da transcrição"] if points else [],
        "pontos_chave": points,
    }


def merge_deterministic_evidence(summary: dict, text: str) -> dict:
    merged = dict(summary)
    model_points = list(merged.get("pontos_chave", []))
    deterministic_points = build_deterministic_chunk_summary(text)["pontos_chave"]
    seen = {point.casefold() for point in model_points if isinstance(point, str)}
    merged["pontos_chave"] = model_points + [
        point for point in deterministic_points
        if point.casefold() not in seen
    ]
    return merged


def _select_critical_facts(facts: list[str], limit: int) -> list[str]:
    ranked = sorted(
        enumerate(facts),
        key=lambda item: (
            bool(_CRITICAL_FACT_PATTERN.search(item[1])),
            len(_CRITICAL_FACT_PATTERN.findall(item[1])),
            item[0],
        ),
        reverse=True,
    )[:limit]
    return [fact for _index, fact in sorted(ranked)]


def _select_boundary_facts(facts: list[str], limit: int) -> list[str]:
    if len(facts) <= limit:
        return facts
    head_size = limit // 2
    return facts[:head_size] + facts[-(limit - head_size):]


def _select_metric_facts(facts: list[str], limit: int) -> list[str]:
    if len(facts) <= limit:
        return facts
    selected = [
        fact for fact in facts
        if _BUSINESS_METRIC_PATTERN.search(fact)
        or _CALENDAR_METRIC_PATTERN.search(fact)
    ][:limit]
    if len(selected) == limit:
        return [fact for fact in facts if fact in selected]
    for fact in _select_critical_facts(facts, 5):
        if fact not in selected:
            selected.append(fact)
        if len(selected) == 15:
            break
    for fact in _select_boundary_facts(facts, limit - len(selected)):
        if fact not in selected:
            selected.append(fact)
        if len(selected) == limit:
            break
    return [fact for fact in facts if fact in selected]


def _bound_summary_fact(fact: str, max_chars: int = 320) -> str:
    compact = re.sub(r"\s+", " ", fact).strip()
    if len(compact) <= max_chars:
        return compact
    shortened = compact[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}…"


def build_analysis_progress(
    analysis: MeetingAnalysis,
    chunks: list[MeetingChunk],
    *,
    now: datetime | None = None,
) -> dict:
    total = max(analysis.total_chunks or 0, 0)
    processed = min(
        sum(chunk.chunk_summary is not None for chunk in chunks), total
    ) if total else 0
    percent = round((processed / total) * 100, 2) if total else 0.0
    is_partial = processed < total
    embedded = min(
        sum(getattr(chunk, "embedding", None) is not None for chunk in chunks),
        total,
    ) if total else 0
    embedding_percent = round((embedded / total) * 100, 2) if total else 0.0

    attempt_started = getattr(
        analysis, "summary_attempt_started_at", None
    )
    attempt_baseline = getattr(
        analysis, "summary_attempt_started_chunks", 0
    ) or 0
    attempt_processed = processed - attempt_baseline
    if attempt_started is None:
        attempt_started = getattr(analysis, "created_at", None)
        attempt_processed = processed

    if total and processed >= total:
        estimate = 0
    elif processed == 0 or attempt_started is None or attempt_processed <= 0:
        estimate = None
    else:
        current = now or datetime.now(timezone.utc)
        started = attempt_started
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        elapsed = max((current - started).total_seconds(), 0)
        estimate = math.ceil(
            (elapsed / attempt_processed) * (total - processed)
        )

    persisted_stage = getattr(analysis, "summary_stage", None)
    persisted_final = bool(getattr(analysis, "summary_is_final", False))
    if persisted_stage:
        summary_stage = persisted_stage
    elif total and processed >= total:
        summary_stage = "COMPLETE"
    elif processed or getattr(analysis, "final_summary", None):
        summary_stage = "PARTIAL"
    else:
        summary_stage = "PRELIMINARY"
    summary_is_final = persisted_final or summary_stage == "COMPLETE"

    return {
        "processed_chunks": processed,
        "total_chunks": total,
        "progress_percent": percent,
        "is_partial": is_partial,
        "estimated_seconds_remaining": estimate,
        "summary_stage": summary_stage,
        "summary_is_final": summary_is_final,
        "summary_progress_percent": percent,
        "embedding_progress_percent": embedding_percent,
        "summary_estimated_seconds_remaining": estimate,
    }


def build_compact_final_summary(chunk_summaries: list[dict]) -> dict:
    grouped = {
        "DECISÃO": [], "AÇÃO": [], "PRAZO": [], "VALOR": [],
        "PROBLEMA": [], "DÚVIDA": [], "EVIDÊNCIA": [], "INSIGHT": [],
    }
    all_facts = []
    structured_fields = {
        "problemas_identificados": "PROBLEMA",
        "decisoes_tomadas": "DECISÃO",
        "duvidas_em_aberto": "DÚVIDA",
        "oportunidades_insights": "INSIGHT",
        "evidencias_importantes": "EVIDÊNCIA",
        "acoes_recomendadas": "AÇÃO",
    }
    for summary in chunk_summaries:
        for field, category in structured_fields.items():
            for value in summary.get(field, []):
                if not isinstance(value, str):
                    continue
                fact = _bound_summary_fact(value)
                if fact and fact not in grouped[category]:
                    grouped[category].append(fact)
                    all_facts.append(fact)
        for point in summary.get("pontos_chave", []):
            if not isinstance(point, str):
                continue
            if ":" not in point:
                fact = point.strip()
                if fact and fact not in grouped["EVIDÊNCIA"]:
                    grouped["EVIDÊNCIA"].append(fact)
                    all_facts.append(fact)
                continue
            prefix, fact = point.split(":", 1)
            prefix = prefix.strip().upper()
            fact = _bound_summary_fact(fact)
            if prefix in grouped and fact and fact not in grouped[prefix]:
                grouped[prefix].append(fact)
                all_facts.append(fact)

    metrics = {}
    quantified_values = [
        fact for fact in grouped["VALOR"]
        if _QUANTIFIED_VALUE_PATTERN.search(fact)
    ]
    explicit_deadlines = [
        fact for fact in grouped["PRAZO"]
        if _EXPLICIT_DEADLINE_PATTERN.search(fact)
    ]
    if quantified_values:
        metrics["valores"] = "; ".join(
            _select_metric_facts(quantified_values, 30)
        )
    if explicit_deadlines:
        metrics["prazos"] = "; ".join(
            _select_metric_facts(explicit_deadlines, 30)
        )
    theme_points = _select_critical_facts(all_facts, 3)
    return {
        "resumo_geral": "; ".join(_select_critical_facts(all_facts, 5)),
        "temas_agrupados": (
            [{"tema": "Pontos principais", "pontos": theme_points}]
            if theme_points else []
        ),
        "problemas_identificados": _select_critical_facts(grouped["PROBLEMA"], 3),
        "decisoes_tomadas": _select_critical_facts(grouped["DECISÃO"], 3),
        "duvidas_em_aberto": _select_critical_facts(grouped["DÚVIDA"], 3),
        "oportunidades_insights": _select_critical_facts(grouped["INSIGHT"], 3),
        "evidencias_importantes": _select_critical_facts(grouped["EVIDÊNCIA"], 3),
        "metricas_negocio": metrics,
        "acoes_recomendadas": _select_critical_facts(grouped["AÇÃO"], 3),
    }


def iter_pending_summaries(chunks: list[MeetingChunk], concurrency: int):
    if concurrency not in (1, 2):
        raise ValueError("A concorrência de chunks deve ser 1 ou 2.")

    def generate(chunk: MeetingChunk):
        return generate_chunk_summary(chunk.clean_content or chunk.content)

    if concurrency == 1:
        for chunk in chunks:
            yield chunk.chunk_index, generate(chunk)
        return

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis-chunk") as executor:
        futures = {executor.submit(generate, chunk): chunk for chunk in chunks}
        try:
            for future in as_completed(futures):
                chunk = futures[future]
                yield chunk.chunk_index, future.result()
        except Exception:
            for future in futures:
                future.cancel()
            raise


def build_single_chunk_final_summary(summary: dict) -> dict:
    themes = summary.get("temas_discutidos", [])
    compact_points = summary.get("pontos_chave", [])
    return {
        "resumo_geral": summary.get("resumo_chunk", ""),
        "temas_agrupados": [
            {"tema": theme, "pontos": [theme]} for theme in themes
        ],
        "problemas_identificados": summary.get("problemas_identificados", []),
        "decisoes_tomadas": summary.get("decisoes_tomadas", []),
        "duvidas_em_aberto": summary.get("duvidas_em_aberto", []),
        "oportunidades_insights": summary.get("oportunidades_insights", []),
        "evidencias_importantes": summary.get(
            "evidencias_importantes", compact_points
        ),
        "metricas_negocio": summary.get("metricas_negocio", {}),
        "acoes_recomendadas": summary.get("acoes_recomendadas", []),
    }


def prepare_analysis(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    transcription = sanitize_transcription(payload.transcription)
    compacted_transcription = clean_transcription(transcription)
    logger.info(
        "meeting_id=%s original_tokens=%d selected_tokens=%d coverage=full",
        payload.meeting_id,
        count_tokens(transcription),
        count_tokens(compacted_transcription),
    )
    chunks = split_text_by_tokens(
        compacted_transcription,
        settings.max_tokens_per_chunk,
        settings.overlap_tokens,
    )
    analysis = MeetingAnalysis(
        external_meeting_id=payload.meeting_id,
        external_user_id=payload.user_id,
        title=payload.title,
        status="PROCESSING",
        final_summary=build_preliminary_summary(compacted_transcription),
        summary_stage="PRELIMINARY",
        summary_is_final=False,
    )
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
        analysis.summary_stage = "PARTIAL"
        analysis.summary_is_final = False
        analysis.error_message = None
        existing_chunks = _analysis_chunks(db, analysis_id)
        analysis.summary_attempt_started_at = datetime.now(timezone.utc)
        analysis.summary_attempt_started_chunks = sum(
            chunk.chunk_summary is not None for chunk in existing_chunks
        )
        db.commit()
        db.refresh(analysis)

        chunks = existing_chunks
        pending = [chunk for chunk in chunks if chunk.chunk_summary is None]
        priority_indices = rank_chunk_indices_for_partial(
            [chunk.clean_content or chunk.content for chunk in pending],
            min(settings.max_llm_chunks, len(pending)),
        )
        priority = [pending[index] for index in priority_indices]
        pending = priority
        chunks_by_index = {chunk.chunk_index: chunk for chunk in chunks}
        started_at = perf_counter()
        for chunk_index, summary in iter_pending_summaries(
            pending, settings.chunk_processing_concurrency
        ):
            current_chunk = chunks_by_index[chunk_index]
            current_chunk.chunk_summary = merge_deterministic_evidence(
                summary, current_chunk.clean_content or current_chunk.content
            )
            completed_summaries = [
                chunk.chunk_summary
                for chunk in chunks
                if chunk.chunk_summary is not None
            ]
            if completed_summaries and all(
                "pontos_chave" in item for item in completed_summaries
            ):
                analysis.final_summary = build_compact_final_summary(
                    completed_summaries
                )
            db.commit()
            logger.info(
                "analysis_id=%s chunk=%d summary_checkpoint=true",
                analysis.id,
                chunk_index,
            )
        logger.info(
            "analysis_id=%s pending_chunks=%d summaries_seconds=%.3f concurrency=%d",
            analysis.id,
            len(pending),
            perf_counter() - started_at,
            settings.chunk_processing_concurrency,
        )
        for chunk in chunks:
            if chunk.chunk_summary is None:
                chunk.chunk_summary = build_deterministic_chunk_summary(
                    chunk.clean_content or chunk.content
                )
        db.commit()
        summaries = [chunk.chunk_summary for chunk in chunks]

        if settings.fast_deterministic_consolidation and all(
            "pontos_chave" in summary for summary in summaries
        ):
            analysis.final_summary = build_compact_final_summary(summaries)
            logger.info("analysis_id=%s deterministic_consolidation=true", analysis.id)
        elif len(summaries) == 1:
            analysis.final_summary = build_single_chunk_final_summary(summaries[0])
            logger.info("analysis_id=%s single_chunk_consolidation=skipped", analysis.id)
        else:
            started_at = perf_counter()
            analysis.final_summary = consolidate_summaries(summaries)
            logger.info("analysis_id=%s consolidation_seconds=%.3f", analysis.id, perf_counter() - started_at)
        analysis.final_summary = complete_missing_fields(
            analysis.final_summary, summaries
        )
        analysis.summary_stage = "COMPLETE"
        analysis.summary_is_final = True
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
