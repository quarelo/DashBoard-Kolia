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


def list_analyses(db: Session, offset: int, limit: int) -> dict:
    total = db.execute(text("SELECT count(*) FROM ai.meeting_analyses")).scalar() or 0
    rows = db.execute(
        text(_BASE_SELECT + " ORDER BY a.created_at DESC, a.id LIMIT :limit OFFSET :offset"),
        {"limit": limit, "offset": offset},
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


def overview(db: Session, recent_limit: int = 5) -> dict:
    rows = db.execute(text(_BASE_SELECT)).all()
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
