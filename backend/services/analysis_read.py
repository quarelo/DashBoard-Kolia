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


def _parse_minutes(raw: Any) -> float | None:
    """DURACAO_MEETING chega como "HH:MM:SS" no CSV — confirmado nos dados
    reais (oito reuniões, ex. "00:26:01", "02:30:12"; a média das oito bate
    com o "69.9" usado como exemplo). Um número puro de minutos também é
    aceito, caso a fonte mude de formato. Sem essa metadata (ou com um valor
    que não bate nenhum dos dois formatos), a reunião fica fora da média —
    não estimamos duração para quem não a informou."""
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    if ":" in text:
        pieces = text.split(":")
        if len(pieces) not in (2, 3):
            return None
        try:
            numbers = [float(piece) for piece in pieces]
        except ValueError:
            return None
        hours, minutes, seconds = (0.0, *numbers) if len(numbers) == 2 else numbers
        total = hours * 60 + minutes + seconds / 60
        return total if total >= 0 else None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    return value if value >= 0 else None


def _month_key(dt_meeting: Any) -> str | None:
    """DT_MEETING é comparado como string (`>=`/`<=`) nos filtros de data, o que
    só produz ordenação correta em ISO `YYYY-MM-DD` — é o formato que assumimos
    aqui. Uma data em outro formato não quebra nada: só fica fora do
    comparativo mensal, que é o comportamento seguro (não inventar um mês)."""
    value = str(dt_meeting or "")
    if len(value) >= 7 and value[4] == "-" and value[:4].isdigit() and value[5:7].isdigit():
        return value[:7]
    return None


def _avg(total: float, count: int) -> float:
    return round(total / count, 1) if count else 0.0


def executive_overview(
    db: Session,
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
    top_n: int = 5,
) -> dict:
    """Agregações para a Dashboard Executiva.

    Mesma fonte e os mesmos filtros de :func:`overview` — leitura pura sobre
    ``ai.meeting_analyses`` já processada pela IA, sem chamar o serviço de IA.

    Uma limitação documentada: ``reclamacoes``/``gaps``/``elogios`` em
    ``top_produtos`` só são atribuídos quando a reunião cita exatamente um
    produto (``final_summary.produto`` com um único item). O resumo guarda
    esses fatos no nível da reunião, não por produto, então uma reunião com
    dois ou mais produtos citados não entra nessa contagem — é uma aproximação
    assumida, não um dado que a IA declarou por produto.
    """
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    query = _BASE_SELECT + ((" WHERE 1=1" + extra_where) if extra_where else "")
    rows = db.execute(text(query), params).all()

    durations: list[float] = []
    product_mentions: dict[str, int] = {}
    product_single_stats: dict[str, dict[str, int]] = {}
    monthly: dict[str, dict[str, float]] = {}
    uf_stats: dict[str, dict[str, float]] = {}
    segmento_stats: dict[str, dict[str, float]] = {}
    theme_counts: dict[str, int] = {}
    risk_ranked: list[dict] = []
    opportunity_ranked: list[dict] = []

    for row in rows:
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        risco = _summary_block(fs, "risco_churn")
        oportunidade = _summary_block(fs, "score_oportunidade")
        sentimento = _summary_block(fs, "sentimento")
        risk_score = int(_num(risco.get("score")))
        opportunity_score = int(_num(oportunidade.get("score")))
        products = _as_list(fs.get("produto"))
        metadata = row.meeting_metadata or {}
        uf_value = str(metadata.get("UF") or "").strip().upper() or None
        segmento_value = str(metadata.get("NOME_SEGMENTO") or "").strip() or None

        duration = _parse_minutes(metadata.get("DURACAO_MEETING"))
        if duration is not None:
            durations.append(duration)

        for product in products:
            product_mentions[product] = product_mentions.get(product, 0) + 1
        if len(products) == 1:
            stats = product_single_stats.setdefault(
                products[0], {"reclamacoes": 0, "gaps": 0, "elogios": 0},
            )
            stats["reclamacoes"] += len(_as_list(fs.get("problemas_identificados")))
            stats["gaps"] += len(_as_list(fs.get("gap_produto")))
            # feedback_produto não carrega polaridade própria; só conta como
            # elogio quando o sentimento geral da reunião já foi classificado
            # como positivo — não inferimos tom a partir do texto livre.
            if sentimento.get("classificacao") == "positivo":
                stats["elogios"] += len(_as_list(fs.get("feedback_produto")))

        month = _month_key(metadata.get("DT_MEETING"))
        if month:
            bucket = monthly.setdefault(month, {"reunioes": 0, "risco": 0.0, "oportunidade": 0.0})
            bucket["reunioes"] += 1
            bucket["risco"] += risk_score
            bucket["oportunidade"] += opportunity_score

        if uf_value:
            bucket = uf_stats.setdefault(uf_value, {"reunioes": 0, "risco": 0.0})
            bucket["reunioes"] += 1
            bucket["risco"] += risk_score

        if segmento_value:
            bucket = segmento_stats.setdefault(segmento_value, {"reunioes": 0, "risco": 0.0, "oportunidade": 0.0})
            bucket["reunioes"] += 1
            bucket["risco"] += risk_score
            bucket["oportunidade"] += opportunity_score

        for evidence in fs.get("evidencias") or []:
            if isinstance(evidence, dict) and evidence.get("categoria"):
                categoria = str(evidence["categoria"])
                theme_counts[categoria] = theme_counts.get(categoria, 0) + 1

        # O CSV não tem coluna de razão social/cliente — `title` é
        # "Reunião <ID_MEETING>", gerado no import (verificado nos dados: as
        # 10 análises atuais têm esse padrão). Não inventamos um nome de
        # cliente que a fonte não fornece; `titulo` é o mesmo identificador
        # que a listagem de reuniões já expõe.
        # `meeting_external_id` é o ID legível do CSV (via core.meetings);
        # `external_meeting_id` (de ai.meeting_analyses) é um UUID interno da
        # IA e só sobra como identificador quando a análise não veio de um
        # import (sem linha em core.meetings).
        ranking_entry = {
            "analysis_id": str(row.analysis_id),
            "external_meeting_id": row.meeting_external_id or str(row.external_meeting_id),
            "titulo": row.title,
            "uf": uf_value,
            "segmento": segmento_value,
        }
        if risk_score > 0:
            risk_ranked.append({**ranking_entry, "score": risk_score,
                                 "motivo": risco.get("justificativa") or ""})
        if opportunity_score > 0:
            opportunity_ranked.append({**ranking_entry, "score": opportunity_score,
                                        "motivo": oportunidade.get("justificativa") or ""})

    top_product_name = max(product_mentions, key=product_mentions.get) if product_mentions else None

    top_produtos = []
    for name, mentions in sorted(product_mentions.items(), key=lambda e: e[1], reverse=True)[:10]:
        entry = {"nome": name, "mencoes": mentions}
        if name in product_single_stats:
            entry.update(product_single_stats[name])
        top_produtos.append(entry)

    risk_ranked.sort(key=lambda e: e["score"], reverse=True)
    opportunity_ranked.sort(key=lambda e: e["score"], reverse=True)

    return {
        "kpis": {
            "total_reunioes": len(rows),
            "duracao_media_minutos": round(sum(durations) / len(durations), 1) if durations else None,
            "produto_mais_citado": top_product_name,
            "mencoes_produto_mais_citado": product_mentions.get(top_product_name) if top_product_name else None,
        },
        "comparativo_mensal": [
            {
                "mes": mes,
                "reunioes": int(bucket["reunioes"]),
                "risco_medio": _avg(bucket["risco"], int(bucket["reunioes"])),
                "oportunidade_media": _avg(bucket["oportunidade"], int(bucket["reunioes"])),
            }
            for mes, bucket in sorted(monthly.items())
        ],
        "top_produtos": top_produtos,
        "temas": [
            {"tema": tema, "ocorrencias": count}
            for tema, count in sorted(theme_counts.items(), key=lambda e: e[1], reverse=True)[:10]
        ],
        "top_uf_risco": sorted(
            (
                {"uf": uf_key, "risco_medio": _avg(bucket["risco"], int(bucket["reunioes"])),
                 "reunioes": int(bucket["reunioes"])}
                for uf_key, bucket in uf_stats.items()
            ),
            key=lambda e: e["risco_medio"], reverse=True,
        ),
        "top_segmentos": sorted(
            (
                {"segmento": seg_key, "reunioes": int(bucket["reunioes"]),
                 "risco_medio": _avg(bucket["risco"], int(bucket["reunioes"])),
                 "oportunidade_media": _avg(bucket["oportunidade"], int(bucket["reunioes"]))}
                for seg_key, bucket in segmento_stats.items()
            ),
            key=lambda e: e["risco_medio"], reverse=True,
        ),
        "top5_risco": risk_ranked[:top_n],
        "top5_oportunidade": opportunity_ranked[:top_n],
    }


def product_meetings(
    db: Session,
    nome: str,
    *,
    uf: str | None = None,
    segmento: str | None = None,
    unidade: str | None = None,
    formato: str | None = None,
    cnae: str | None = None,
    dt_meeting_from: str | None = None,
    dt_meeting_to: str | None = None,
) -> dict:
    """Reuniões por trás dos números de um produto no Gráfico de Produto.

    Mesma limitação de :func:`executive_overview`: só entra reunião que cita
    esse produto sozinho (``final_summary.produto`` com um único item) — é a
    mesma aproximação usada para contar ``reclamacoes``/``gaps``/``elogios``
    por produto, então o número na barra e a lista de reuniões por trás dele
    batem sempre.
    """
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    query = _BASE_SELECT + ((" WHERE 1=1" + extra_where) if extra_where else "")
    rows = db.execute(text(query), params).all()

    reclamacoes: list[dict] = []
    gaps: list[dict] = []
    elogios: list[dict] = []

    for row in rows:
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        products = _as_list(fs.get("produto"))
        if len(products) != 1 or products[0] != nome:
            continue

        sentimento = _summary_block(fs, "sentimento")
        metadata = row.meeting_metadata or {}
        meeting_entry = {
            "analysis_id": str(row.analysis_id),
            "external_meeting_id": row.meeting_external_id or str(row.external_meeting_id),
            "titulo": row.title,
            "uf": str(metadata.get("UF") or "").strip().upper() or None,
            "segmento": str(metadata.get("NOME_SEGMENTO") or "").strip() or None,
        }

        problemas = _as_list(fs.get("problemas_identificados"))
        if problemas:
            reclamacoes.append({**meeting_entry, "itens": problemas})

        gap_itens = _as_list(fs.get("gap_produto"))
        if gap_itens:
            gaps.append({**meeting_entry, "itens": gap_itens})

        # Mesmo critério do agregado: feedback só vira elogio quando o
        # sentimento geral da reunião já foi classificado como positivo.
        if sentimento.get("classificacao") == "positivo":
            feedback_itens = _as_list(fs.get("feedback_produto"))
            if feedback_itens:
                elogios.append({**meeting_entry, "itens": feedback_itens})

    return {"produto": nome, "reclamacoes": reclamacoes, "gaps": gaps, "elogios": elogios}


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
