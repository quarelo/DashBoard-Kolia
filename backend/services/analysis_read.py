"""Leitura das análises geradas pela IA para alimentar o dashboard.

As análises vivem no schema ``ai`` (mesmo banco), escritas pelo serviço de IA.
Nem toda análise tem uma linha correspondente em ``core.meetings``: uma análise
pode ter sido enviada direto para a IA. Por isso a fonte da verdade aqui é
``ai.meeting_analyses``, com JOIN opcional em ``core.meetings`` pelo ``analysis_id``
para recuperar metadados de importação e a transcrição.

Somente leitura — nenhuma migration do backend gerencia o schema ``ai``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# Colunas de ai.meeting_analyses + metadados da reunião importada (quando existir).
_SELECT_TEMPLATE = """
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
        m.source_metadata   AS meeting_metadata{extra}
    FROM ai.meeting_analyses a
    LEFT JOIN core.meetings m ON m.analysis_id = a.id
"""

# `m.transcription` fica fora do SELECT das agregações de propósito. É a coluna
# mais gorda do banco (15 MB somando as 912 reuniões, 77 kB na maior) e nenhuma
# agregação lê o texto — só `get_analysis`, que carrega uma reunião. As quatro
# agregações varrem a tabela inteira sem LIMIT, então arrastá-la custava 1,32 s
# por chamada contra 0,14 s sem ela (201 análises, Postgres remoto). A Página de
# Produto faz três dessas chamadas em paralelo e esperava 3,5 s para receber
# 1 KB de JSON de insights.
_BASE_SELECT = _SELECT_TEMPLATE.format(extra="")

# Só a leitura de uma análise, onde a transcrição é o próprio conteúdo da tela.
_DETAIL_SELECT = _SELECT_TEMPLATE.format(
    extra=",\n        m.transcription     AS meeting_transcription",
)


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


# Reuniões que citam este produto, de propósito **sem** exigir que o citem
# sozinho: é a condição mais frouxa das duas, então as agregações por produto
# continuam aplicando a regra de produto único em Python (abaixo), e nenhuma
# reunião que elas contavam antes deixa de chegar aqui. O que este `WHERE` faz é
# poupar o banco de mandar — e o Python de desserializar — o `final_summary` das
# reuniões que não têm nada a ver com o produto: 60 das 201 análises não citam
# produto nenhum, e as que citam espalham-se por dezenas de nomes.
#
# De quebra, a contagem de linhas que passam por aqui é exatamente
# `mencoes_totais` (toda menção, inclusive em reunião multi-produto), que antes
# a Página de Produto só conseguia agregando o `/executive` inteiro.
_CITES_PRODUCT = " AND a.final_summary -> 'produto' @> jsonb_build_array(CAST(:produto AS text))"


def _product_query(extra_where: str) -> str:
    """`_BASE_SELECT` restrito às reuniões que citam o produto de `:produto`."""
    return _BASE_SELECT + " WHERE 1=1" + _CITES_PRODUCT + extra_where


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
        text(_DETAIL_SELECT + " WHERE a.id = :id"), {"id": str(analysis_id)}
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
    rows = db.execute(text(_product_query(extra_where)), {**params, "produto": nome}).all()

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


# A natureza de um gap, por vocabulário. Léxico e não embedding de propósito:
# as categorias abaixo saíram da contagem de palavras dos 391 gaps da carga
# atual (`integração` 79, `ausência`/`falta` 138, `automação`/`automática` 80,
# `nativa` 36, `controle` 28), então a regra é derivada do dado em vez de
# adivinhada, e roda sem chamar modelo — o que importa porque a tela abre em
# ~70ms e uma passada de embedding por gap custaria 52ms cada, quente.
#
# Medido sobre os 391 gaps: 85,2% caem numa categoria. O resto é heterogêneo de
# verdade ("Falta de líder de produção definido na empresa") e inclui extração
# ruim da IA ("Nenhum gap identificado no portfólio TOTVS." veio como gap), daí
# `Não classificado` ser uma fatia visível na resposta em vez de ser escondida:
# o tamanho dela é o aviso de que a taxonomia não cobre tudo.
#
# Rótulo único por gap, não multi-rótulo, para a soma das fatias fechar com o
# total de gaps. Empate resolve pela ordem desta lista.
_GAP_NATURE_RULES: tuple[tuple[str, str], ...] = (
    ("Integração", r"integra|conect|api\b|interface com|sincroniz|conciliac|troca de dados|webservice|middleware|vincula(r|cao|ndo) (direta|entre|dados)"),
    ("Automação de fluxo", r"automa|automatic|manual|manualmente|jobs?\b|robo|sem intervenc|fluxo de aprovac"),
    ("Fiscal e tributário", r"fiscal|tribut|ncm|notas? fiscal|notas fiscais|icms|sped|nfe|nf-e|e-cfc|cfop|imposto|obrigac|contabil|licitac"),
    ("Relatório e indicador", r"relatori|indicador|dashboard|painel|bi\b|analytics|visualizar hist|tendencia|grafico|metrica|kpi|funil|previsibilidade|gargalo|previsoes|visualizacao"),
    ("Controle e rastreabilidade", r"controle|rastrea|estoque|invent|cadastro|etiqueta|codigo de barras|validade|lote\b|apontamento|historico de|banco de talentos"),
    ("Capacidade e performance", r"limite|limitac|performance|lentid|volume|capacidade|processamento|escalabilidade|requisic|infraestrutura|compatibilidade|servidor"),
    ("Financeiro e cobrança", r"financeir|boleto|cobranc|comiss|faturamento|pagamento|parcela|credito|adiantamento|reajuste|precific|pix\b|maquinin|multa"),
    ("Customização e parametrização", r"customiza|parametriz|campo novo|campos adicionais|configurav|desenvolvimento|personaliza|autonomia para|edicao de|editar"),
    ("Usabilidade", r"usabilidade|layout|interface|acessibilidade|facilidade de uso|complexidade|dificuldade (de uso|tecnica|em)|intuitiv|experiencia do usuario|botao|simplificada"),
    ("Serviço e implantação", r"implantac|prazo|suporte|treinamento|consultoria|horas contratadas|documentac|contrato|plano advanced|licenciamento|migrac|descontinuac|porte da empresa"),
)
_GAP_NATURE_COMPILED = tuple((name, re.compile(pattern)) for name, pattern in _GAP_NATURE_RULES)
GAP_NATURE_UNCLASSIFIED = "Não classificado"


def _strip_accents(value: str) -> str:
    """Os padrões acima são escritos sem acento para não precisarem de variante
    por grafia — `integração`, `integracao` e `INTEGRAÇÃO` caem no mesmo."""
    decomposed = unicodedata.normalize("NFD", value.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def classify_gap(gap: str) -> str:
    """A categoria de um gap, ou ``GAP_NATURE_UNCLASSIFIED``.

    Ganha a categoria com mais ocorrências de vocabulário; a ordem de
    ``_GAP_NATURE_RULES`` decide empate (e é por isso que `Integração` vem antes
    de `Financeiro`: "integração do meio de pagamento" é gap de integração).
    """
    plain = _strip_accents(gap)
    best = max(
        (len(pattern.findall(plain)), -index, name)
        for index, (name, pattern) in enumerate(_GAP_NATURE_COMPILED)
    )
    hits, _, name = best
    return name if hits else GAP_NATURE_UNCLASSIFIED


def _empty_health_bucket() -> dict[str, int]:
    return {"reunioes": 0, "reclamacoes": 0, "gaps": 0, "elogios": 0}


def _bump_health(bucket: dict[str, int], *, reclamacoes: int, gaps: int, elogios: int) -> None:
    bucket["reunioes"] += 1
    bucket["reclamacoes"] += reclamacoes
    bucket["gaps"] += gaps
    bucket["elogios"] += elogios


def product_insights(
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
    """Dados de apoio à Página de Produto: saúde mês a mês, cruzamento com
    segmento/UF/CNAE e personas envolvidas, para um produto específico.

    Mesma limitação de :func:`executive_overview` e :func:`product_meetings`:
    só entra reunião que cita esse produto sozinho (``final_summary.produto``
    com um único item) — consistência com o Gráfico de Produto do dashboard
    executivo. Ver ``docs/product-page-analytics.md``.

    A exceção é ``mencoes_totais``, que conta toda reunião que cita o produto,
    inclusive junto com outros — é o número de ``top_produtos[].mencoes`` no
    ``/executive``, servido aqui para a tela não precisar das duas chamadas.
    """
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    rows = db.execute(text(_product_query(extra_where)), {**params, "produto": nome}).all()

    monthly: dict[str, dict[str, int]] = {}
    persona_counts: dict[str, int] = {}
    nature_counts: dict[str, int] = {}
    reunioes_detalhadas = 0

    for row in rows:
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        products = _as_list(fs.get("produto"))
        if len(products) != 1 or products[0] != nome:
            continue
        reunioes_detalhadas += 1

        sentimento = _summary_block(fs, "sentimento")
        reclamacoes = len(_as_list(fs.get("problemas_identificados")))
        gap_itens = _as_list(fs.get("gap_produto"))
        gaps = len(gap_itens)
        for gap in gap_itens:
            categoria = classify_gap(gap)
            nature_counts[categoria] = nature_counts.get(categoria, 0) + 1
        # Mesmo critério do agregado e de `product_meetings`: feedback só vira
        # elogio quando o sentimento geral da reunião já foi positivo.
        elogios = (
            len(_as_list(fs.get("feedback_produto")))
            if sentimento.get("classificacao") == "positivo" else 0
        )

        metadata = row.meeting_metadata or {}
        month = _month_key(metadata.get("DT_MEETING"))
        if month:
            _bump_health(monthly.setdefault(month, _empty_health_bucket()),
                         reclamacoes=reclamacoes, gaps=gaps, elogios=elogios)

        for persona in _as_list(fs.get("persona")):
            persona_counts[persona] = persona_counts.get(persona, 0) + 1

    return {
        "produto": nome,
        # Toda reunião que cita o produto, mesmo junto com outros — o mesmo
        # número que `top_produtos[].mencoes` do `/executive` dá para este
        # produto, pelos mesmos filtros. Vive aqui para a Página de Produto não
        # precisar carregar o `/executive` inteiro só para ler um KPI, e porque
        # `top_produtos` corta no Top 10: um produto fora dos dez mais citados
        # não tinha de onde tirar as menções.
        "mencoes_totais": len(rows),
        "reunioes_detalhadas": reunioes_detalhadas,
        "saude_mensal": [
            {"mes": mes, **bucket} for mes, bucket in sorted(monthly.items())
        ],
        # A natureza dos gaps substituiu a quebra por UF/segmento/CNAE: aquelas
        # três eram a mesma contagem de reclamação/gap/elogio num terceiro
        # recorte, e com mediana de 1 reunião detalhada por produto cada uma
        # rendia uma barra só. Esta conta **itens**, não reuniões — mediana de 3
        # gaps por produto, máximo 22 —, então tem material para um gráfico.
        "natureza_gaps": sorted(
            ({"categoria": chave, "ocorrencias": n} for chave, n in nature_counts.items()),
            key=lambda e: (e["categoria"] == GAP_NATURE_UNCLASSIFIED, -e["ocorrencias"]),
        ),
        "personas": sorted(
            ({"nome": chave, "ocorrencias": n} for chave, n in persona_counts.items()),
            key=lambda e: e["ocorrencias"], reverse=True,
        ),
    }


def product_gap_texts(
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
    limit: int = 200,
) -> list[str]:
    """Os textos de ``gap_produto`` das reuniões deste produto, sem repetição.

    É o insumo que o roteador manda para a IA casar contra o catálogo. Fica aqui
    e não na IA porque o recorte "reuniões deste produto, sob estes filtros"
    depende de ``core.meetings``, que a IA não lê. `limit` é o mesmo teto do
    ``GapCoverageRequest`` da IA — cortar aqui dá uma resposta parcial em vez de
    um 422 numa carga maior.
    """
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    rows = db.execute(text(_product_query(extra_where)), {**params, "produto": nome}).all()
    seen: dict[str, None] = {}
    for row in rows:
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        products = _as_list(fs.get("produto"))
        if len(products) != 1 or products[0] != nome:
            continue
        for gap in _as_list(fs.get("gap_produto")):
            cleaned = gap.strip()
            if cleaned:
                seen.setdefault(cleaned, None)
    return list(seen)[:limit]


# As cinco métricas do perfil de qualidade, na ordem em que a tela as mostra.
# `maior_e_melhor` existe porque a barra divergente precisa saber de que lado
# está o bom: 10 pontos acima da média é ótimo em oportunidade e péssimo em
# risco de churn, e sem isso tudo verde para o lado direito mentiria.
_QUALITY_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("risco_churn", "Risco de churn", False),
    ("oportunidade", "Oportunidade", True),
    ("satisfacao", "Reuniões com sentimento positivo", True),
    ("gaps_por_reuniao", "Gaps por reunião", False),
    ("duvidas_por_reuniao", "Dúvidas em aberto por reunião", False),
)


def _quality_metrics(rows: list) -> tuple[dict[str, float], int]:
    """As cinco médias sobre as reuniões de produto único que vieram em `rows`."""
    risco = oportunidade = positivos = gaps = duvidas = 0.0
    total = 0
    for row in rows:
        fs = row.final_summary if isinstance(row.final_summary, dict) else {}
        if len(_as_list(fs.get("produto"))) != 1:
            continue
        total += 1
        risco += _num(_summary_block(fs, "risco_churn").get("score"))
        oportunidade += _num(_summary_block(fs, "score_oportunidade").get("score"))
        if _summary_block(fs, "sentimento").get("classificacao") == "positivo":
            positivos += 1
        gaps += len(_as_list(fs.get("gap_produto")))
        duvidas += len(_as_list(fs.get("duvidas_em_aberto")))
    if not total:
        return {key: 0.0 for key, _label, _up in _QUALITY_METRICS}, 0
    return {
        "risco_churn": round(risco / total, 1),
        "oportunidade": round(oportunidade / total, 1),
        "satisfacao": round(positivos / total * 100, 1),
        "gaps_por_reuniao": round(gaps / total, 2),
        "duvidas_por_reuniao": round(duvidas / total, 2),
    }, total


def product_quality_profile(
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
    """O produto em cinco métricas, cada uma ao lado da média do portfólio.

    A comparação é o ponto, não a métrica solta: com mediana de 1 reunião
    detalhada por produto, uma série temporal ou um ranking não dizem nada, mas
    "risco 20 pontos acima da média do portfólio" diz, mesmo com n=1. Por isso
    a resposta sempre carrega `reunioes` nos dois lados — a tela precisa poder
    avisar quando o número vem de uma reunião só.

    A base de comparação é a mesma população do numerador (reuniões que citam um
    produto só, sob os mesmos filtros), senão a média do portfólio incluiria
    reuniões multi-produto e de produto nenhum, e a diferença mediria isso em
    vez de medir o produto.
    """
    extra_where, params = _build_filters(
        uf=uf, segmento=segmento, unidade=unidade, formato=formato,
        cnae=cnae, dt_meeting_from=dt_meeting_from, dt_meeting_to=dt_meeting_to,
    )
    product_rows = db.execute(
        text(_product_query(extra_where)), {**params, "produto": nome},
    ).all()
    # O portfólio inteiro: a única leitura desta tela que não é recortada por
    # produto. Sem a transcrição (ver `_BASE_SELECT`) são ~0,14s nas 201
    # análises; é o preço da linha de base.
    portfolio_rows = db.execute(
        text(_BASE_SELECT + ((" WHERE 1=1" + extra_where) if extra_where else "")), params,
    ).all()

    produto_valores, produto_reunioes = _quality_metrics(product_rows)
    portfolio_valores, portfolio_reunioes = _quality_metrics(portfolio_rows)

    return {
        "produto": nome,
        "reunioes": produto_reunioes,
        "reunioes_portfolio": portfolio_reunioes,
        "metricas": [
            {
                "chave": chave,
                "rotulo": rotulo,
                "valor": produto_valores[chave],
                "media_portfolio": portfolio_valores[chave],
                "maior_e_melhor": maior_e_melhor,
            }
            for chave, rotulo, maior_e_melhor in _QUALITY_METRICS
        ],
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
