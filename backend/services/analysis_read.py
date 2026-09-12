"""Leitura das análises geradas pela IA para alimentar o dashboard.

As análises vivem no schema ``ai`` (mesmo banco), escritas pelo serviço de IA.
Nem toda análise tem uma linha correspondente em ``core.meetings``: uma análise
pode ter sido enviada direto para a IA. Por isso a fonte da verdade aqui é
``ai.meeting_analyses``, com JOIN opcional em ``core.meetings`` pelo ``analysis_id``
para recuperar metadados de importação e a transcrição.

Somente leitura — nenhuma migration do backend gerencia o schema ``ai``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# Colunas de ai.meeting_analyses + metadados da reunião importada (quando existir).
_BASE_SELECT = """
    SELECT
        a.id                AS analysis_id,
        a.external_meeting_id,
        a.title,
        a.status,
        a.total_tokens,
        a.total_chunks,
        a.summary_stage,
        a.summary_is_final,
        a.error_message,
        a.created_at,
        a.updated_at,
        a.final_summary,
        m.id                AS meeting_id,
        m.external_id       AS meeting_external_id,
        m.source_metadata   AS meeting_metadata,
        m.transcription     AS meeting_transcription
    FROM ai.meeting_analyses a
    LEFT JOIN core.meetings m ON m.analysis_id = a.id
"""


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return []


def _summary_block(final_summary: Any, key: str) -> dict:
    if isinstance(final_summary, dict) and isinstance(final_summary.get(key), dict):
        return final_summary[key]
    return {}


def to_list_item(row: Any) -> dict:
    """Projeção enxuta de uma linha para a listagem do dashboard."""
    fs = row.final_summary if isinstance(row.final_summary, dict) else {}
    risco = _summary_block(fs, "risco_churn")
    oportunidade = _summary_block(fs, "score_oportunidade")
    sentimento = _summary_block(fs, "sentimento")
    meeting = None
    if row.meeting_id is not None:
        meeting = {
            "id": str(row.meeting_id),
            "external_id": row.meeting_external_id,
            "metadata": row.meeting_metadata or {},
        }
    return {
        "analysis_id": str(row.analysis_id),
        "external_meeting_id": str(row.external_meeting_id),
        "title": row.title,
        "status": row.status,
        "summary_stage": row.summary_stage,
        "summary_is_final": bool(row.summary_is_final),
        "total_chunks": row.total_chunks,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "risk_score": int(_num(risco.get("score"))),
        "risk_reason": risco.get("justificativa") or "",
        "opportunity_score": int(_num(oportunidade.get("score"))),
        "opportunity_reason": oportunidade.get("justificativa") or "",
        "sentiment": sentimento.get("classificacao") or "não identificado",
        "sentiment_reason": sentimento.get("justificativa") or "",
        "products": _as_list(fs.get("produto")),
        "personas": _as_list(fs.get("persona")),
        "meeting": meeting,
    }


def _build_filters(
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
) -> tuple[str, dict]:
    """Build WHERE clauses and params for JSONB filters on core.meetings.source_metadata."""
    clauses: list[str] = []
    params: dict[str, str] = {}
    if uf:
        clauses.append("m.source_metadata->>'UF' = :uf")
        params["uf"] = uf.upper()
    if cnae:
        clauses.append("m.source_metadata->>'CNAE' = :cnae")
        params["cnae"] = cnae
    if formato:
        clauses.append("lower(m.source_metadata->>'FORMATO_MEETING') = lower(:formato)")
        params["formato"] = formato
    if segmento:
        clauses.append("lower(m.source_metadata->>'NOME_SEGMENTO') LIKE :segmento")
        params["segmento"] = f"%{segmento.lower()}%"
    if unidade:
        clauses.append("lower(m.source_metadata->>'NOME_UNIDADE') LIKE :unidade")
        params["unidade"] = f"%{unidade.lower()}%"
    if dt_meeting_from:
        clauses.append("m.source_metadata->>'DT_MEETING' >= :dt_from")
        params["dt_from"] = dt_meeting_from
    if dt_meeting_to:
        clauses.append("m.source_metadata->>'DT_MEETING' <= :dt_to")
        params["dt_to"] = dt_meeting_to
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_analyses(
    db: Session,
    offset: int,
    limit: int,
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
) -> dict:
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    # When filters target core.meetings columns the JOIN must match; rows
    # without a linked meeting are excluded by any metadata filter.
    count_query = "SELECT count(*) FROM ai.meeting_analyses a"
    if extra_where:
        count_query += " LEFT JOIN core.meetings m ON m.analysis_id = a.id WHERE 1=1" + extra_where
    total = db.execute(text(count_query), params).scalar() or 0
    rows = db.execute(
        text(_BASE_SELECT + (" WHERE 1=1" + extra_where if extra_where else "")
             + " ORDER BY a.created_at DESC, a.id LIMIT :limit OFFSET :offset"),
        {**params, "limit": limit, "offset": offset},
    ).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [to_list_item(row) for row in rows],
    }


def get_analysis(db: Session, analysis_id: UUID) -> dict | None:
    row = db.execute(
        text(_BASE_SELECT + " WHERE a.id = :id"), {"id": str(analysis_id)}
    ).first()
    if row is None:
        return None
    item = to_list_item(row)
    item["final_summary"] = row.final_summary if isinstance(row.final_summary, dict) else {}
    item["error_message"] = row.error_message
    item["total_tokens"] = row.total_tokens
    item["transcription"] = row.meeting_transcription
    return item


def top_risk_and_opportunity(
    db: Session,
    limit: int = 5,
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
) -> dict:
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    done_filter = " WHERE a.summary_is_final = true"
    if extra_where:
        done_filter += extra_where
    params["top_n"] = limit

    risk_rows = db.execute(
        text(
            _BASE_SELECT + done_filter
            + " ORDER BY (a.final_summary->'risco_churn'->>'score')::float DESC NULLS LAST"
            + " LIMIT :top_n"
        ),
        params,
    ).all()

    opp_rows = db.execute(
        text(
            _BASE_SELECT + done_filter
            + " ORDER BY (a.final_summary->'score_oportunidade'->>'score')::float DESC NULLS LAST"
            + " LIMIT :top_n"
        ),
        params,
    ).all()

    return {
        "limit": limit,
        "top_churn_risk": [to_list_item(r) for r in risk_rows],
        "top_opportunity": [to_list_item(r) for r in opp_rows],
    }


def _parse_duration(value: Any) -> float | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        minutes = float(s)
        if minutes >= 0:
            return minutes
        return None
    except ValueError:
        pass
    parts = s.split(":")
    if len(parts) in (2, 3):
        try:
            hours = float(parts[0])
            mins = float(parts[1])
            secs = float(parts[2]) if len(parts) == 3 else 0
            return hours * 60 + mins + secs / 60
        except ValueError:
            pass
    return None


def executive_overview(db: Session) -> dict:
    rows = db.execute(text(_BASE_SELECT)).all()

    durations: list[float] = []
    product_counts: dict[str, int] = {}
    product_metrics: dict[str, dict[str, int]] = {}
    monthly: dict[str, dict[str, Any]] = {}
    segment_counts: dict[str, int] = {}
    segment_risk_opp: dict[str, dict[str, Any]] = {}
    uf_data: dict[str, dict[str, Any]] = {}

    for row in rows:
        item = to_list_item(row)
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        metadata = row.meeting_metadata or {}

        dur = _parse_duration(metadata.get("DURACAO_MEETING"))
        if dur is not None:
            durations.append(dur)

        reclamacoes = len(_as_list(fs.get("problemas_identificados")))
        gaps = len(_as_list(fs.get("gap_produto")))
        elogios = len(_as_list(fs.get("feedback_produto")))
        for product in item["products"]:
            product_counts[product] = product_counts.get(product, 0) + 1
            if product not in product_metrics:
                product_metrics[product] = {"reclamacoes": 0, "gaps": 0, "elogios": 0}
            product_metrics[product]["reclamacoes"] += reclamacoes
            product_metrics[product]["gaps"] += gaps
            product_metrics[product]["elogios"] += elogios

        dt = str(metadata.get("DT_MEETING", ""))
        month = dt[:7] if len(dt) >= 7 else ""
        if month:
            if month not in monthly:
                monthly[month] = {"reunioes": 0, "risk_sum": 0.0, "opp_sum": 0.0}
            monthly[month]["reunioes"] += 1
            monthly[month]["risk_sum"] += item["risk_score"]
            monthly[month]["opp_sum"] += item["opportunity_score"]

        segmento = str(metadata.get("NOME_SEGMENTO", "")).strip()
        if segmento:
            segment_counts[segmento] = segment_counts.get(segmento, 0) + 1
            if segmento not in segment_risk_opp:
                segment_risk_opp[segmento] = {"risk_sum": 0.0, "opp_sum": 0.0, "count": 0}
            segment_risk_opp[segmento]["risk_sum"] += item["risk_score"]
            segment_risk_opp[segmento]["opp_sum"] += item["opportunity_score"]
            segment_risk_opp[segmento]["count"] += 1

        uf = str(metadata.get("UF", "")).strip()
        if uf:
            if uf not in uf_data:
                uf_data[uf] = {"risk_sum": 0.0, "count": 0}
            uf_data[uf]["risk_sum"] += item["risk_score"]
            uf_data[uf]["count"] += 1

    top_product = max(product_counts.items(), key=lambda x: x[1]) if product_counts else ("", 0)

    comparativo = sorted([
        {
            "mes": mes,
            "reunioes": d["reunioes"],
            "risco_medio": round(d["risk_sum"] / d["reunioes"], 1),
            "oportunidade_media": round(d["opp_sum"] / d["reunioes"], 1),
        }
        for mes, d in monthly.items()
    ], key=lambda x: x["mes"])[-4:]

    top_produtos = sorted([
        {"nome": nome, **product_metrics[nome]}
        for nome in product_metrics
    ], key=lambda x: product_counts[x["nome"]], reverse=True)[:5]

    top_segmentos = sorted([
        {"segmento": seg, "reunioes": count}
        for seg, count in segment_counts.items()
    ], key=lambda x: x["reunioes"], reverse=True)[:5]

    top_uf = sorted([
        {"uf": uf, "risco_medio": round(d["risk_sum"] / d["count"], 1), "reunioes": d["count"]}
        for uf, d in uf_data.items()
    ], key=lambda x: x["risco_medio"], reverse=True)[:5]

    risco_opp = sorted([
        {
            "segmento": seg,
            "risco_medio": round(d["risk_sum"] / d["count"], 1),
            "oportunidade_media": round(d["opp_sum"] / d["count"], 1),
        }
        for seg, d in segment_risk_opp.items()
    ], key=lambda x: x["risco_medio"], reverse=True)

    return {
        "kpis": {
            "total_reunioes": len(rows),
            "duracao_media_minutos": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "produto_mais_citado": top_product[0],
            "mencoes_produto_mais_citado": top_product[1],
        },
        "comparativo_mensal": comparativo,
        "top_produtos": top_produtos,
        "top_segmentos": top_segmentos,
        "top_uf_risco": top_uf,
        "risco_oportunidade_segmento": risco_opp,
    }


def overview(
    db: Session,
    recent_limit: int = 5,
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
) -> dict:
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    query = _BASE_SELECT + ((" WHERE 1=1" + extra_where) if extra_where else "")
    rows = db.execute(text(query), params).all()
    items = [to_list_item(row) for row in rows]

    sentiment_keys = ("positivo", "neutro", "negativo", "misto", "não identificado")
    sentiment = {key: 0 for key in sentiment_keys}
    risk_buckets = {"baixo": 0, "medio": 0, "alto": 0}
    product_counts: dict[str, int] = {}
    risk_values: list[int] = []
    opp_values: list[int] = []
    analyzed = processing = failed = high_risk = 0

    for item in items:
        status = (item["status"] or "").upper()
        if item["summary_is_final"] or status in {"DASHBOARD_READY", "EMBEDDING", "DONE"}:
            analyzed += 1
        elif status.startswith("FAILED") or "ERROR" in status:
            failed += 1
        else:
            processing += 1

        sentiment[item["sentiment"]] = sentiment.get(item["sentiment"], 0) + 1

        risk = item["risk_score"]
        risk_values.append(risk)
        if risk >= 67:
            risk_buckets["alto"] += 1
            high_risk += 1
        elif risk >= 34:
            risk_buckets["medio"] += 1
        else:
            risk_buckets["baixo"] += 1

        opp_values.append(item["opportunity_score"])
        for product in item["products"]:
            product_counts[product] = product_counts.get(product, 0) + 1

    top_products = sorted(
        ({"name": name, "count": count} for name, count in product_counts.items()),
        key=lambda entry: entry["count"], reverse=True,
    )[:8]

    return {
        "total": len(items),
        "analyzed": analyzed,
        "processing": processing,
        "failed": failed,
        "avg_risk": round(sum(risk_values) / len(risk_values), 1) if risk_values else 0.0,
        "avg_opportunity": round(sum(opp_values) / len(opp_values), 1) if opp_values else 0.0,
        "high_risk_count": high_risk,
        "sentiment": sentiment,
        "risk_buckets": risk_buckets,
        "top_products": top_products,
        "recent": items[:recent_limit],
    }
