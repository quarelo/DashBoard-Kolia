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
_FINANCIAL_VALUE_PATTERN = re.compile(
    r"(?:R\$|reais?|milh(?:ão|ões))", re.IGNORECASE
)
_CHURN_SIGNAL_PATTERN = re.compile(
    r"(?:cancel|churn|insatisfeit|risco de perder|não retid|deixar de|encerrar)",
    re.IGNORECASE,
)
_NON_CHURN_CANCELLATION_PATTERN = re.compile(
    r"\b(?:pedido|ordem|fatura|cliente)\s+(?:foi\s+)?cancelad",
    re.IGNORECASE,
)
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
    actions = [
        text for text in selected
        if re.search(r"\b(?:enviar|entregar|fazer|agendar|substitu|refazer|vamos)\w*", text, re.IGNORECASE)
    ][:10]
    problems = [
        text for text in selected
        if re.search(r"\b(?:problema|erro|risco|dúvida|pendente|não|sem)\w*", text, re.IGNORECASE)
    ][:8]
    quantified = [text for text in selected if _FINANCIAL_VALUE_PATTERN.search(text)][:12]

    return {
        "produto": [],
        "persona": [],
        "sentimento": {
            "classificacao": "não identificado",
            "justificativa": "Aguardando análise semântica completa.",
        },
        "risco_churn": {"score": 0, "justificativa": "Aguardando análise semântica completa."},
        "oportunidade_comercial": [],
        "score_oportunidade": {"score": 0, "justificativa": "Aguardando análise semântica completa."},
        "budget": {
            "identificado": bool(quantified),
            "valor": "; ".join(quantified),
            "contexto": "Valores ou quantidades encontrados na transcrição." if quantified else "Não identificado.",
        },
        "gap_produto": [],
        "problemas_identificados": problems,
        "feedback_produto": [],
        "evidencias": [
            {"categoria": "prévia", "insight": text, "trecho": text}
            for text in selected[:12]
        ],
        "recomendacao_acao": actions,
        "duvidas_em_aberto": [],
    }


def build_deterministic_chunk_summary(text: str) -> dict:
    preview = build_preliminary_summary(text)
    points: list[str] = []
    categories = (
        ("AÇÃO", preview["recomendacao_acao"]),
        ("PROBLEMA", preview["problemas_identificados"]),
        ("EVIDÊNCIA", [item["trecho"] for item in preview["evidencias"]]),
    )
    seen = set()
    for category, facts in categories:
        for fact in facts:
            normalized = fact.casefold()
            if normalized not in seen:
                points.append(f"{category}: {fact}")
                seen.add(normalized)
    if preview["budget"]["identificado"]:
        for fact in preview["budget"]["valor"].split("; "):
            if fact:
                points.append(f"BUDGET: {fact}")
    return {
        "resumo_chunk": "; ".join(item["trecho"] for item in preview["evidencias"]),
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


def _source_sentences(source_texts: list[str]) -> list[str]:
    return [
        re.sub(r"\s+", " ", raw_sentence).strip()
        for text in source_texts
        for raw_sentence in re.split(r"(?<=[.!?])\s+", text)
        if raw_sentence.strip()
    ]


def _extract_source_facts(source_texts: list[str]) -> dict[str, list[str]]:
    """Recover high-signal facts from the transcript when a small model labels them poorly."""
    sentences = _source_sentences(source_texts)
    all_text = " ".join(sentences)
    facts = {key: [] for key in (
        "produto", "persona", "sentimento", "budget", "gap", "problema",
        "oportunidade", "evidencia",
    )}

    def add(key: str, value: str, limit: int = 8) -> None:
        value = _bound_summary_fact(value)
        if value and value.casefold() not in {item.casefold() for item in facts[key]}:
            facts[key].append(value)
            del facts[key][limit:]

    if re.search(r"\b(?:TotoCRM|CRM|força de vendas)\b", all_text, re.I):
        add("produto", "TotoCRM / CRM de automação de força de vendas", 3)
    if re.search(r"\b(?:DataSuite|DataSoup|PD4000)\b", all_text, re.I):
        add("produto", "Integração com ERP/DataSuite e PD4000", 3)
    for role in (
        "gestor", "gerente", "diretor", "especialista de vendas", "vendedores",
        "consultores", "representantes", "marketing", "infraestrutura", "TI",
    ):
        if re.search(rf"\b{re.escape(role)}\b", all_text, re.I):
            add("persona", role)

    positive = [s for s in sentences if re.search(
        r"\b(?:interessante|gostaria|faz sentido|perfeito|prezamos?|boa|legal|concordo)\b",
        s, re.I)]
    caution = [s for s in sentences if re.search(
        r"\b(?:caro|inviável|problema|presos? no banco|não conseguimos|não tenho)\b",
        s, re.I)]
    if positive and caution:
        facts["sentimento"] = ["Interesse positivo, com ressalvas sobre custo, aderência e riscos técnicos."]
    elif positive:
        facts["sentimento"] = ["Percepção positiva e interesse em avançar."]
    elif caution:
        facts["sentimento"] = ["Percepção cautelosa, com ressalvas sobre custos e limitações técnicas."]

    for sentence in sentences:
        if re.search(r"R\$\s*\d|\b(?:licenças?|licenciamento)\b", sentence, re.I):
            if not re.search(r"\b(?:clientes?|pedidos?|atividades?|quilômetros?)\b", sentence, re.I):
                add("budget", sentence, 6)
        if re.search(
            r"(?:\bPDF\b|boleto|ordem de compra|\bEDI\b|"
            r"usuários?.{0,35}presos? no banco|não.{0,30}roadmap|"
            r"não.{0,30}(?:recurso|funcionalidade|atende)|"
            r"customiza(?:ção|r).{0,40}(?:limita|não|falt))",
            sentence,
            re.I,
        ):
            add("gap", sentence)
        if re.search(
            r"(?:dificuldade|inviável|caro|não conseguimos|presos? no banco|"
            r"Windows\s*11|substitui(?:ção|r).{0,40}(?:máquina|equipamento)|"
            r"usuários?.{0,35}presos? no banco|não.{0,30}roadmap)",
            sentence,
            re.I,
        ):
            if not (
                re.search(r"dificuldade", sentence, re.I)
                and not re.search(r"(?:integra|substitu|infra|licen)", sentence, re.I)
            ):
                add("problema", sentence)
        if re.search(r"(?:CRM|cloud|nuvem|IA|indicador|licença|consultoria)", sentence, re.I):
            add("oportunidade", sentence, 6)
    facts["evidencia"] = positive[:3] + caution[:3]
    facts["budget"].sort(
        key=lambda item: (not bool(re.search(r"R\$\s*\d", item)), item)
    )
    return facts


def build_compact_final_summary(
    chunk_summaries: list[dict], source_texts: list[str] | None = None
) -> dict:
    grouped = {
        "PRODUTO": [], "PERSONA": [], "SENTIMENTO": [], "CHURN": [],
        "OPORTUNIDADE": [], "BUDGET": [], "GAP": [], "PROBLEMA": [],
        "FEEDBACK": [], "DÚVIDA": [], "AÇÃO": [], "EVIDÊNCIA": [],
    }
    structured_fields = {
        "problemas_identificados": "PROBLEMA",
        "duvidas_em_aberto": "DÚVIDA",
        "oportunidade_comercial": "OPORTUNIDADE",
        "gap_produto": "GAP",
        "feedback_produto": "FEEDBACK",
        "recomendacao_acao": "AÇÃO",
        # Compatibilidade com chunks persistidos antes do novo contrato.
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
        for point in summary.get("pontos_chave", []):
            if not isinstance(point, str):
                continue
            if ":" not in point:
                fact = point.strip()
                if fact and fact not in grouped["EVIDÊNCIA"]:
                    grouped["EVIDÊNCIA"].append(fact)
                continue
            prefix, fact = point.split(":", 1)
            prefix = prefix.strip().upper()
            fact = _bound_summary_fact(fact)
            if prefix in grouped and fact and fact not in grouped[prefix]:
                grouped[prefix].append(fact)

    budget_facts = [
        fact for fact in grouped["BUDGET"]
        if _FINANCIAL_VALUE_PATTERN.search(fact)
    ]
    grouped["CHURN"] = [
        fact for fact in grouped["CHURN"]
        if _CHURN_SIGNAL_PATTERN.search(fact)
        and not _NON_CHURN_CANCELLATION_PATTERN.search(fact)
    ]
    opportunities = _select_critical_facts(grouped["OPORTUNIDADE"], 3)
    churn_signals = _select_critical_facts(grouped["CHURN"], 3)
    sentiment_facts = grouped["SENTIMENTO"]
    sentiment_text = " ".join(sentiment_facts).casefold()
    if any(word in sentiment_text for word in ("negativ", "insatisfeit", "frustr")):
        sentiment = "negativo"
    elif any(word in sentiment_text for word in ("positiv", "satisfeit", "gost")):
        sentiment = "positivo"
    elif sentiment_facts:
        sentiment = "neutro"
    else:
        sentiment = "não identificado"
    evidence = []
    for category, facts in grouped.items():
        for fact in facts:
            evidence.append({
                "categoria": category.casefold(),
                "insight": fact,
                "trecho": fact,
            })
            if len(evidence) == 24:
                break
        if len(evidence) == 24:
            break
    source_facts = _extract_source_facts(source_texts or []) if source_texts else {}
    source_budget = source_facts.get("budget", [])
    products = source_facts.get("produto", []) or _select_critical_facts(grouped["PRODUTO"], 3)
    personas = source_facts.get("persona", []) or _select_critical_facts(grouped["PERSONA"], 3)
    source_sentiment = source_facts.get("sentimento", [])
    if source_sentiment:
        sentiment = "misto" if "ressalva" in source_sentiment[0] else "positivo"
        sentiment_facts = source_sentiment
    return {
        "produto": products[:3],
        "persona": personas[:3],
        "sentimento": {
            "classificacao": sentiment,
            "justificativa": "; ".join(sentiment_facts[:3]) or "Não identificado nos trechos processados.",
        },
        "risco_churn": {
            "score": min(100, 40 + 15 * len(churn_signals)) if churn_signals else 0,
            "justificativa": "; ".join(churn_signals) or "Nenhum sinal explícito identificado.",
        },
        "oportunidade_comercial": opportunities,
        "score_oportunidade": {
            "score": min(100, 40 + 15 * len(opportunities)) if opportunities else 0,
            "justificativa": "; ".join(opportunities) or "Nenhuma oportunidade explícita identificada.",
        },
        "budget": {
            "identificado": bool(source_budget or budget_facts),
            "valor": "; ".join(_select_metric_facts(
                source_facts.get("budget", []) or budget_facts, 3
            )),
            "contexto": "; ".join((source_facts.get("budget", []) or grouped["BUDGET"])[:3]) or "Não identificado.",
        },
        "gap_produto": (
            source_facts.get("gap", [])
            + [fact for fact in _select_critical_facts(grouped["GAP"], 3)
               if fact not in source_facts.get("gap", [])]
        )[:3] or _select_critical_facts(grouped["GAP"], 3),
        "problemas_identificados": (
            source_facts.get("problema", [])
            + [fact for fact in _select_critical_facts(grouped["PROBLEMA"], 3)
               if fact not in source_facts.get("problema", [])]
        )[:3] or _select_critical_facts(grouped["PROBLEMA"], 3),
        "feedback_produto": _select_critical_facts(grouped["FEEDBACK"], 3),
        "evidencias": evidence,
        "recomendacao_acao": _select_critical_facts(grouped["AÇÃO"], 3),
        "duvidas_em_aberto": _select_critical_facts(grouped["DÚVIDA"], 3),
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
    return build_compact_final_summary([summary])


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
                    completed_summaries,
                    [chunk.clean_content or chunk.content for chunk in chunks],
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
            analysis.final_summary = build_compact_final_summary(
                summaries,
                [chunk.clean_content or chunk.content for chunk in chunks],
            )
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
