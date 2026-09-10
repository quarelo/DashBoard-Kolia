import json
import re
from typing import Any

import httpx

from src.app.core.config import settings
from src.app.services.token_service import count_tokens
from src.app.services.scoring_service import ChurnMotive, OpportunityMotive


class OllamaError(RuntimeError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


_CHUNK_CATEGORY_ALIASES = {
    "DÚVIDAS": "DÚVIDA",
    "OPORTUNIDADES": "OPORTUNIDADE",
    "PRODUTOS": "PRODUTO",
}
_CHUNK_CATEGORIES = {
    "PRODUTO", "PERSONA", "SENTIMENTO", "CHURN", "OPORTUNIDADE",
    "BUDGET", "GAP", "PROBLEMA", "FEEDBACK", "DÚVIDA", "AÇÃO",
    "EVIDÊNCIA",
}


def _normalize_chunk_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = []
    for point in summary.get("pontos_chave", []):
        if not isinstance(point, str) or ":" not in point:
            continue
        category, fact = point.split(":", 1)
        category = _CHUNK_CATEGORY_ALIASES.get(
            category.strip().upper(), category.strip().upper()
        )
        fact = fact.strip()
        if category in _CHUNK_CATEGORIES and fact:
            normalized.append(f"{category}: {fact}")
        if len(normalized) == 12:
            break
    return {
        "pontos_chave": normalized,
        # Kept alongside the free-text points: the schema already guarantees these
        # are catalogue codes, so scoring reads them instead of matching wording.
        "motivos_churn": _valid_codes(summary.get("motivos_churn"), CHURN_MOTIVE_CODES),
        "motivos_oportunidade": _valid_codes(
            summary.get("motivos_oportunidade"), OPPORTUNITY_MOTIVE_CODES),
    }


def _valid_codes(values: Any, allowed: list[str]) -> list[str]:
    """Keep declared codes only, de-duplicated, order preserved.

    The schema constrains the model, but a salvaged or legacy response can still
    carry anything, and an unknown code must never reach the scoring table.
    """
    if not isinstance(values, list):
        return []
    seen: list[str] = []
    for value in values:
        if isinstance(value, str) and value in allowed and value not in seen:
            seen.append(value)
    return seen


def _salvage_chunk_summary(raw: str) -> dict[str, Any] | None:
    marker = '"pontos_chave"'
    marker_index = raw.find(marker)
    array_start = raw.find("[", marker_index + len(marker))
    if marker_index < 0 or array_start < 0:
        return None
    completed_strings = re.findall(
        r'"((?:\\.|[^"\\])*)"', raw[array_start + 1:]
    )
    points = []
    for encoded in completed_strings:
        try:
            points.append(json.loads(f'"{encoded}"'))
        except json.JSONDecodeError:
            continue
    normalized = _normalize_chunk_summary({"pontos_chave": points})
    return normalized if normalized["pontos_chave"] else None


def _extract_deterministic_chunk_points(text: str) -> list[str]:
    points: list[str] = []

    def add(category: str, fact: str) -> None:
        compact = " ".join(fact.split()).strip(" ,.;:")
        point = f"{category}: {compact}"
        if compact and point not in points:
            points.append(point)

    for match in re.finditer(
        r"\b(TotoCRM|TOTVS\s+(?:ERP|CRM|Fluig|Protheus|Datasul|RM|WMS)|"
        r"DataSuite|DataSoup|PD4000)\b",
        text,
        re.IGNORECASE,
    ):
        add("PRODUTO", match.group(1))

    for match in re.finditer(
        r"\b((?:time|área|parte)\s+(?:comercial|de vendas|de marketing)|"
        r"(?:gerente|gestor|diretor)\s+(?:comercial|de vendas|de TI|de infraestrutura)|"
        r"(?:vendedores?|consultores?|representantes?|distribuidores?|"
        r"marketing|infraestrutura|TI)\b[^.;!?]{0,50})",
        text,
        re.IGNORECASE,
    ):
        add("PERSONA", match.group(1))

    for match in re.finditer(
        r"\[(?:CLIENTE|TOTVS)\s*-\s*([^\]]{2,80})\]", text, re.IGNORECASE
    ):
        add("PERSONA", match.group(1))

    dissatisfaction = re.search(
        r"\b(insatisfeit[oa]s?\s+com\s+[^.;!?]{2,100})", text, re.IGNORECASE
    )
    if dissatisfaction:
        add("SENTIMENTO", dissatisfaction.group(1))
        add("FEEDBACK", dissatisfaction.group(1))

    churn = re.search(
        r"\b(podemos\s+cancelar\s+se\s+[^.;!?]{2,120})", text, re.IGNORECASE
    )
    if churn:
        add("CHURN", churn.group(1))

    gap = re.search(
        r"\b(?:precisamos?|necessitamos?)\s+([^.;!?]{2,120}recurso\s+que\s+"
        r"não\s+(?:encontramos|existe|temos)[^.;!?]{0,80})",
        text,
        re.IGNORECASE,
    )
    if gap:
        add("GAP", gap.group(1))

    for match in re.finditer(
        r"([^.!?]{0,100}(?:PDF|boleto|ordem de compra|EDI|importa(?:ção|r)|"
        r"customiza(?:ção|r)|usuários? ficam presos no banco)[^.!?]{0,120})",
        text,
        re.IGNORECASE,
    ):
        add("GAP", match.group(1))

    for match in re.finditer(
        r"R\$\s*\d[\d.]*(?:,\d+)?(?:\s*(?:mil|milh(?:ão|ões)))?",
        text,
        re.IGNORECASE,
    ):
        add("BUDGET", match.group(0))

    for match in re.finditer(r"(?:^|[.!]\s+)([^.!?]{2,180}\?)", text):
        add("DÚVIDA", match.group(1))

    for match in re.finditer(
        r"\b(CRM)\s+para\s+(\d+)\s+(pessoas|usuários|licenças|vendedores)\b",
        text,
        re.IGNORECASE,
    ):
        add(
            "OPORTUNIDADE",
            f"{match.group(1).upper()} para {match.group(2)} {match.group(3).lower()}",
        )

    weekday_pattern = (
        r"segunda|terça|quarta|quinta|sexta|sábado|domingo"
    )
    for match in re.finditer(
        rf"\b(?:eu\s+)?vou\s+(.{{1,60}}?)\s+na\s+"
        rf"(({weekday_pattern})\s*-?\s*feira)\b",
        text,
        re.IGNORECASE,
    ):
        action = re.sub(
            r"\[\s*L\d+\s*\]\s*: ?", " ", match.group(1),
            flags=re.IGNORECASE,
        )
        action = " ".join(action.split()).strip(" ,.;:")
        weekday = re.sub(r"\s*-\s*", "-", match.group(2).lower())
        if action:
            add("AÇÃO", f"{action} na {weekday}")
    return points[:12]


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    candidates = [raw.strip()]
    if "```" in raw:
        fenced = raw.strip().removeprefix("```json").removeprefix("```")
        candidates.append(fenced.removesuffix("```").strip())
    opening = raw.find("{")
    if opening >= 0:
        candidates.append(raw[opening:])
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed, _end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# Motive codes are constrained by the schema itself, so the model cannot invent
# a label and scoring never depends on its phrasing. This removes the old
# failure mode: free text like "potencial de perda" had to match a regex
# vocabulary, and 250 of 500 real churn signals did not.
CHURN_MOTIVE_CODES = [m.value for m in ChurnMotive]
OPPORTUNITY_MOTIVE_CODES = [m.value for m in OpportunityMotive]

CHUNK_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "pontos_chave": {
            "type": "array",
            "items": {
                "type": "string",
                "maxLength": 180,
                "pattern": (
                    "^(PRODUTO|PERSONA|SENTIMENTO|CHURN|OPORTUNIDADE|BUDGET|"
                    "GAP|PROBLEMA|FEEDBACK|DÚVIDA|AÇÃO|EVIDÊNCIA): .+$"
                ),
            },
            "minItems": 1,
            "maxItems": 12,
        },
        "motivos_churn": {
            "type": "array",
            "items": {"type": "string", "enum": CHURN_MOTIVE_CODES},
            "maxItems": 5,
        },
        "motivos_oportunidade": {
            "type": "array",
            "items": {"type": "string", "enum": OPPORTUNITY_MOTIVE_CODES},
            "maxItems": 5,
        },
    },
    "required": ["pontos_chave", "motivos_churn", "motivos_oportunidade"],
    "additionalProperties": False,
}

# Without the catalogue in the prompt the model has no idea what these fields
# mean, so asking for them anyway only costs tokens and truncations.
CHUNK_SUMMARY_SCHEMA_NO_MOTIVES = {
    "type": "object",
    "properties": {"pontos_chave": CHUNK_SUMMARY_SCHEMA["properties"]["pontos_chave"]},
    "required": ["pontos_chave"],
    "additionalProperties": False,
}

FINAL_LIST_SCHEMA = {
    "type": "array",
    "items": {"type": "string", "maxLength": 180},
    "maxItems": 3,
}

EVIDENCE_SCHEMA = {
    "type": "array",
    "maxItems": 24,
    "items": {
        "type": "object",
        "properties": {
            "categoria": {"type": "string", "maxLength": 50},
            "insight": {"type": "string", "maxLength": 180},
            "trecho": {"type": "string", "maxLength": 300},
        },
        "required": ["categoria", "insight", "trecho"],
        "additionalProperties": False,
    },
}

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justificativa": {"type": "string", "maxLength": 240},
    },
    "required": ["score", "justificativa"],
    "additionalProperties": False,
}

FINAL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "produto": FINAL_LIST_SCHEMA,
        "persona": FINAL_LIST_SCHEMA,
        "sentimento": {
            "type": "object",
            "properties": {
                "classificacao": {"type": "string", "enum": ["positivo", "neutro", "negativo", "misto", "não identificado"]},
                "justificativa": {"type": "string", "maxLength": 240},
            },
            "required": ["classificacao", "justificativa"],
            "additionalProperties": False,
        },
        "risco_churn": SCORE_SCHEMA,
        "oportunidade_comercial": FINAL_LIST_SCHEMA,
        "score_oportunidade": SCORE_SCHEMA,
        "budget": {
            "type": "object",
            "properties": {
                "identificado": {"type": "boolean"},
                "valor": {"type": "string", "maxLength": 180},
                "contexto": {"type": "string", "maxLength": 240},
            },
            "required": ["identificado", "valor", "contexto"],
            "additionalProperties": False,
        },
        "gap_produto": FINAL_LIST_SCHEMA,
        "problemas_identificados": FINAL_LIST_SCHEMA,
        "feedback_produto": FINAL_LIST_SCHEMA,
        "evidencias": EVIDENCE_SCHEMA,
        "recomendacao_acao": FINAL_LIST_SCHEMA,
        "duvidas_em_aberto": FINAL_LIST_SCHEMA,
    },
    "required": [
        "produto", "persona", "sentimento", "risco_churn",
        "oportunidade_comercial", "score_oportunidade", "budget",
        "gap_produto", "problemas_identificados", "feedback_produto",
        "evidencias", "recomendacao_acao", "duvidas_em_aberto",
    ],
    "additionalProperties": False,
}


def missing_fields(final_summary: dict[str, Any], *, include_empty: bool = False) -> list[str]:
    """Required fields the summary does not answer.

    Absent or null is always missing. An empty list is only missing when asked for:
    during the pipeline an empty `produto` usually means the transcript names no
    product, and refilling it invites the model to invent one. On an explicit
    request from someone looking at the card, the empty is what they want retried.
    """
    def unanswered(name: str) -> bool:
        if name not in final_summary or final_summary[name] is None:
            return True
        value = final_summary[name]
        return include_empty and isinstance(value, (list, dict, str)) and not value

    return [name for name in FINAL_SUMMARY_SCHEMA["required"] if unanswered(name)]


def complete_missing_fields(
    final_summary: dict[str, Any],
    chunk_summaries: list[dict],
    *,
    include_empty: bool = False,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    properties = FINAL_SUMMARY_SCHEMA["properties"]
    missing = missing_fields(final_summary, include_empty=include_empty)
    if not missing:
        return dict(final_summary)
    missing_schema = {
        "type": "object",
        "properties": {name: properties[name] for name in missing},
        "required": missing,
        "additionalProperties": False,
    }
    prompt = (
        "Preencha somente os campos ausentes indicados pelo schema. Use apenas "
        "os fatos dos resumos parciais, não altere campos existentes e não "
        "invente fatos.\n\nJSON PARCIAL:\n"
        f"{json.dumps(final_summary, ensure_ascii=False)}\n\nRESUMOS:\n"
        f"{json.dumps(chunk_summaries, ensure_ascii=False)}"
    )
    completion = _generate_json(
        prompt,
        missing_schema,
        False,
        max(settings.ollama_consolidation_num_predict, 768),
        settings.consolidation_model,
        client=client,
    )
    merged = dict(final_summary)
    for name in missing:
        if name in completion:
            merged[name] = completion[name]
    return merged


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    client: httpx.Client | None,
    timeout: float,
) -> dict[str, Any]:
    response = None
    for attempt in range(settings.ollama_read_timeout_retries + 1):
        try:
            if client is None:
                response = httpx.post(url, json=payload, timeout=timeout)
            else:
                response = client.post(url, json=payload, timeout=timeout)
            break
        except httpx.ReadTimeout as error:
            if attempt >= settings.ollama_read_timeout_retries:
                raise OllamaError(
                    f"Não foi possível acessar o Ollama: {error}"
                ) from error
        except httpx.HTTPError as error:
            raise OllamaError(f"Não foi possível acessar o Ollama: {error}") from error

    if response is None:
        raise OllamaError("O Ollama não retornou uma resposta.")

    try:
        data = response.json()
    except ValueError as error:
        raise OllamaResponseError("O Ollama retornou uma resposta HTTP sem JSON válido.") from error

    error_message = str(data.get("error", ""))
    if response.status_code == 404 or "not found" in error_message.lower():
        raise OllamaModelNotFoundError(
            f"Modelo do Ollama não encontrado: {error_message or payload['model']}. "
            "Execute ./ia/install-model.sh para baixar ou trocar o modelo configurado."
        )
    if response.is_error:
        raise OllamaError(
            f"Ollama retornou HTTP {response.status_code}: {error_message or response.text}"
        )
    return data


def _generate_json(
    prompt: str,
    schema: dict[str, Any],
    think: bool,
    num_predict: int,
    model: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    data = _post_json(
        settings.ollama_generate_url,
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "format": schema,
            "think": think,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
        },
        client=client,
        timeout=settings.ollama_generate_timeout_seconds,
    )
    raw_response = data.get("response")
    if not isinstance(raw_response, str):
        raise OllamaResponseError("Resposta do Ollama não contém o campo textual 'response'.")
    raw_candidates = [raw_response]
    parsed = _extract_json_object(raw_response)
    if parsed is None and data.get("done_reason") == "length":
        data = _post_json(
            settings.ollama_generate_url,
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": settings.ollama_keep_alive,
                "format": schema,
                "think": think,
                "options": {
                    "temperature": 0,
                    "num_predict": max(num_predict * 2, 384),
                },
            },
            client=client,
            timeout=settings.ollama_generate_timeout_seconds,
        )
        raw_response = data.get("response")
        if not isinstance(raw_response, str):
            raise OllamaResponseError(
                "Resposta do Ollama não contém o campo textual 'response'."
            )
        raw_candidates.append(raw_response)
        parsed = _extract_json_object(raw_response)
    if parsed is None and settings.ollama_json_repair_enabled:
        repair_data = _post_json(
            settings.ollama_generate_url,
            {
                "model": model,
                "prompt": (
                    "Repare o texto abaixo e devolva somente um objeto JSON válido "
                    "que respeite o schema solicitado. Não acrescente fatos.\n\n"
                    f"TEXTO COM ERRO:\n{raw_response[:8000]}"
                ),
                "stream": False,
                "keep_alive": settings.ollama_keep_alive,
                "format": schema,
                "think": False,
                "options": {"temperature": 0, "num_predict": min(num_predict, 192)},
            },
            client=client,
            timeout=settings.ollama_generate_timeout_seconds,
        )
        repaired_raw = repair_data.get("response")
        if isinstance(repaired_raw, str):
            raw_candidates.append(repaired_raw)
            parsed = _extract_json_object(repaired_raw)
    if parsed is None and "pontos_chave" in schema.get("properties", {}):
        for candidate in reversed(raw_candidates):
            parsed = _salvage_chunk_summary(candidate)
            if parsed is not None:
                break
    if parsed is None:
        raise OllamaResponseError(
            "O modelo retornou JSON inválido para a análise "
            f"(resposta com {len(raw_response)} caracteres; "
            f"done_reason={data.get('done_reason')}; eval_count={data.get('eval_count')})."
        )
    if not isinstance(parsed, dict):
        raise OllamaResponseError("O JSON da análise precisa ser um objeto.")
    return parsed


MOTIVE_CATALOGUE = """Além de pontos_chave, classifique o trecho nos catálogos abaixo, devolvendo
apenas os códigos que o trecho sustenta. Listas vazias são a resposta correta
quando não houver sinal; não force uma classificação.

motivos_churn:
  AMEACA_CANCELAMENTO    cliente fala em cancelar, encerrar ou rescindir
  INSATISFACAO_EXPLICITA cliente demonstra insatisfação ou frustração
  MENCAO_CONCORRENTE     cliente cita outro fornecedor ou alternativa
  RECLAMACAO_PRODUTO     cliente relata falha, erro ou limitação do produto
  INATIVIDADE_PROLONGADA cliente sem uso, sem compra ou sem retorno há tempo

motivos_oportunidade:
  PEDIDO_EXPANSAO        cliente pede ampliar contrato, licenças ou escopo
  MENCAO_BUDGET          cliente cita orçamento, verba ou valor disponível
  PRAZO_DEFINIDO         há data ou prazo concreto para decisão ou entrega
  INTERESSE_NOVO_MODULO  cliente demonstra interesse em produto ainda não usado
  ELOGIO_CLIENTE         cliente elogia produto, entrega ou atendimento

"""


def chunk_num_predict(clean_content: str) -> int:
    """Output budget scaled to the chunk, because one setting cannot fit both sizes.

    A truncated answer costs the whole call again at double the budget, so the
    budget has to clear the answer the chunk actually warrants. Measured on real
    chunks: a ~74-token CSV meeting is fastest at 256 and slower above it, while a
    2000-token chunk truncated on 6 of 6 calls at 256 and on 1 of 6 at 512 — 132s
    against 227s for the same six chunks.

    A quarter of the input lands on both of those points; the floor and the ceiling
    keep a tiny chunk from starving and a huge one from paying for tokens the model
    never produces.
    """
    estimated = count_tokens(clean_content) // 4
    return max(settings.ollama_chunk_num_predict,
               min(estimated, settings.ollama_chunk_num_predict_max))


def generate_chunk_summary(
    clean_content: str,
    *,
    client: httpx.Client | None = None,
    metadata_context: str | None = None,
) -> dict[str, Any]:
    motive_block = MOTIVE_CATALOGUE if settings.chunk_motive_classification else ""
    context_block = (
        f"\nCONTEXTO COMERCIAL DA REUNIÃO:\n{metadata_context}\n\n"
        "Use este contexto para calibrar a análise: o tipo de cliente (lead vs.\n"
        "customer) muda a lente (prospecção vs. retenção); o NPS baixo com menção\n"
        "a concorrente é churn iminente; a faixa de faturamento indica o porte.\n"
        "Não repita o contexto nos pontos_chave — ele serve como referência.\n"
        if metadata_context else ""
    )
    prompt = f"""Você é um especialista em análise de reuniões corporativas.
{context_block}Analise somente o trecho e retorne JSON apenas com pontos_chave. Diferencie
claramente o que é uma demonstração hipotética do vendedor do que é uma
necessidade, opinião ou decisão real do cliente.
Use no máximo 6 pontos curtos. Prefixe cada ponto com exatamente uma categoria
entre PRODUTO, PERSONA, SENTIMENTO, CHURN, OPORTUNIDADE, BUDGET, GAP,
PROBLEMA, FEEDBACK, DÚVIDA, AÇÃO ou EVIDÊNCIA, seguida de dois-pontos e do
fato concreto. OPORTUNIDADE é venda ou expansão de item já existente no
portfólio TOTVS; GAP é necessidade que o portfólio atual não atende. BUDGET
é somente orçamento, preço, investimento ou quantidade de licenças discutida
para esta compra; não classifique métricas de exemplo (clientes, pedidos,
atividades, quilômetros ou valores de demonstração) como budget. CHURN só pode
ser usado com cancelamento, intenção de sair, insatisfação explícita ou risco
de perda do fornecedor; não use a palavra "cancelado" de um pedido como churn.
SENTIMENTO deve refletir a percepção geral do cliente, não o sentimento de um
exemplo narrado pelo vendedor. PERSONA deve identificar a função profissional
quando ela estiver explícita (vendas, marketing, gestão, TI, infraestrutura,
consultor ou representante). Nunca devolva apenas nomes de categorias.
Preserve nomes, números e negações. Copie apenas ações explicitamente
mencionadas; não crie novas ações. O trecho contém fatos relevantes: extraia pelo menos um
deles. Não invente fatos.

{motive_block}TRECHO:
{clean_content}"""
    summary = _generate_json(
        prompt,
        CHUNK_SUMMARY_SCHEMA if settings.chunk_motive_classification
        else CHUNK_SUMMARY_SCHEMA_NO_MOTIVES,
        settings.ollama_chunk_think,
        chunk_num_predict(clean_content),
        settings.chunk_model,
        client=client,
    )
    normalized = _normalize_chunk_summary(summary)
    if not normalized["pontos_chave"]:
        raise OllamaResponseError(
            "O modelo não retornou pontos-chave categorizados para o trecho."
        )
    deterministic = _extract_deterministic_chunk_points(clean_content)
    merged = []
    for point in [*deterministic, *normalized["pontos_chave"]]:
        if point not in merged:
            merged.append(point)
        if len(merged) == 12:
            break
    return {
        "pontos_chave": merged,
        # Carry the catalogue codes through: rebuilding the dict here used to drop
        # them, leaving scoring back on wording-based inference.
        "motivos_churn": normalized.get("motivos_churn", []),
        "motivos_oportunidade": normalized.get("motivos_oportunidade", []),
    }


def consolidate_summaries(
    chunk_summaries: list[dict],
    *,
    client: httpx.Client | None = None,
    metadata_context: str | None = None,
) -> dict[str, Any]:
    summaries_json = json.dumps(chunk_summaries, ensure_ascii=False)
    context_block = (
        f"\nCONTEXTO COMERCIAL DA REUNIÃO:\n{metadata_context}\n\n"
        "Use este contexto ao consolidar: o tipo de cliente (lead vs. customer)\n"
        "define se a reunião é prospecção ou retenção; o NPS influencia o peso\n"
        "do risco de churn; a faixa de faturamento indica o porte do negócio.\n"
        "Não repita esses dados nos campos — eles calibram sua interpretação.\n"
        if metadata_context else ""
    )
    prompt = f"""Você é um especialista sênior em análise de reuniões de venda
B2B da TOTVS. Consolide os resumos parciais em um objeto JSON com exatamente
as chaves do schema. Reconstrua a reunião, não apenas conte os rótulos.
Identifique produto TOTVS, persona profissional, sentimento geral do cliente,
risco de churn (0-100), oportunidade comercial apenas para algo existente no
portfólio, score da oportunidade (0-100), budget, gaps, problemas, feedback,
evidências, recomendações e dúvidas em aberto.
{context_block}Regras obrigatórias:
- Produto e persona devem ser preenchidos quando houver qualquer evidência
  explícita nos resumos; não retorne lista vazia se houver CRM, vendedor,
  marketing, gestor, consultor, representante, TI ou infraestrutura.
- Sentimento é da reunião inteira: interesse/elogios indicam positivo,
  preocupação com custo indica misto ou positivo com ressalva. Não confunda
  exemplo de dashboard com opinião do cliente.
- Churn só recebe score acima de 0 com evidência de cancelamento do contrato,
  intenção de trocar de fornecedor, insatisfação explícita ou risco de perda.
  Pedido cancelado, cliente não retido e oportunidade perdida são métricas,
  não churn por si só.
- Budget contém somente valores, preços, investimentos ou licenças da
  negociação. Separe métricas operacionais como clientes, pedidos, atividades,
  quilômetros e valores usados em exemplos de tela.
- Oportunidade é expansão/venda de produto ou serviço TOTVS; gap é algo que o
  portfólio não atende. Não transforme troca de computador em gap de produto.
- Em evidencias, associe cada insight ao trecho literal mais próximo disponível
  nos resumos. Remova duplicações e descarte fatos sem sustentação.
Quando não houver informação, use lista vazia, score 0, "não identificado" ou
identificado=false. Os resumos têm pontos prefixados por categoria, mas os
rótulos podem estar errados: valide o sentido do texto antes de consolidar.

RESUMOS PARCIAIS:
{summaries_json}"""
    return _generate_json(
        prompt,
        FINAL_SUMMARY_SCHEMA,
        settings.ollama_consolidation_think,
        settings.ollama_consolidation_num_predict,
        settings.consolidation_model,
        client=client,
    )


def product_classification_schema(candidate_names: list[str]) -> dict[str, Any]:
    """Enum built from the candidates themselves, not a fixed list in the code.

    Same mechanism as CHUNK_SUMMARY_SCHEMA's motivos_churn/motivos_oportunidade:
    the enum makes an out-of-catalogue name impossible to return, not just
    discouraged by the prompt.
    """
    return {
        "type": "object",
        "properties": {
            "produtos_identificados": {
                "type": "array",
                "items": {"type": "string", "enum": candidate_names},
                "maxItems": min(len(candidate_names), 3),
            },
        },
        "required": ["produtos_identificados"],
        "additionalProperties": False,
    }


def classify_products(
    evidence_text: str,
    candidates: list[tuple[str, str]],
    *,
    client: httpx.Client | None = None,
) -> list[str]:
    """Pick, from up to 5 real catalogue candidates, which ones the meeting mentions.

    `candidates` already comes from a pgvector similarity search against
    ai.products (see product_service.find_candidate_products) — this call never
    sees the whole catalogue, only the closest matches. Returning an empty list
    is the correct answer when none of the candidates actually apply; nothing
    here pressures the model into forcing a match.
    """
    if not candidates:
        return []
    names = [name for name, _description in candidates]
    catalogue_block = "\n".join(
        f"- {name}: {description}" for name, description in candidates
    )
    prompt = f"""Você recebeu uma lista fechada de produtos TOTVS, já
pré-selecionados por similaridade com o conteúdo da reunião. Releia o
conteúdo abaixo e decida quais desses candidatos a reunião realmente
menciona. Nunca escreva um nome fora da lista de candidatos. Devolva lista
vazia se nenhum candidato se aplica de fato; não force uma escolha.

CANDIDATOS:
{catalogue_block}

CONTEÚDO DA REUNIÃO:
{evidence_text}"""
    result = _generate_json(
        prompt,
        product_classification_schema(names),
        False,
        192,
        settings.consolidation_model,
        client=client,
    )
    identified = result.get("produtos_identificados")
    if not isinstance(identified, list):
        return []
    seen: list[str] = []
    for name in identified:
        if isinstance(name, str) and name in names and name not in seen:
            seen.append(name)
    return seen


def generate_embedding(
    text: str, *, client: httpx.Client | None = None
) -> list[float]:
    data = _post_json(
        settings.ollama_embed_url,
        {"model": settings.embedding_model, "input": text},
        client=client,
        timeout=settings.ollama_embedding_timeout_seconds,
    )
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
        raise OllamaResponseError("O Ollama não retornou uma lista de embeddings.")
    embedding = embeddings[0]
    if len(embedding) != settings.embedding_dim:
        raise OllamaResponseError(
            f"Embedding retornou {len(embedding)} dimensões; esperado {settings.embedding_dim}."
        )
    if not all(isinstance(value, (int, float)) for value in embedding):
        raise OllamaResponseError("O embedding retornado contém valores não numéricos.")
    return [float(value) for value in embedding]


def generate_chat_answer(
    prompt: str, *, client: httpx.Client | None = None
) -> str:
    data = _post_json(
        settings.ollama_generate_url,
        {
            "model": settings.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "think": False,
            "options": {
                "temperature": settings.chat_temperature,
                "num_predict": settings.chat_num_predict,
                "num_ctx": settings.chat_context_length,
            },
        },
        client=client,
        timeout=settings.chat_generate_timeout_seconds,
    )
    raw_response = data.get("response")
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise OllamaResponseError(
            "Resposta do Ollama não contém uma resposta textual para o chat."
        )
    return raw_response.strip()
