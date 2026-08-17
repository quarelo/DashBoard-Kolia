import json
import re
from typing import Any

import httpx

from src.app.core.config import settings


class OllamaError(RuntimeError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


_CHUNK_CATEGORY_ALIASES = {"DÚVIDAS": "DÚVIDA"}
_CHUNK_CATEGORIES = {
    "DECISÃO", "AÇÃO", "PRAZO", "VALOR", "PROBLEMA", "DÚVIDA",
    "EVIDÊNCIA", "INSIGHT",
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
        if len(normalized) == 4:
            break
    return {"pontos_chave": normalized}


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
    points = []
    for match in re.finditer(
        r"\b(CRM)\s+para\s+(\d+)\s+(pessoas|usuários|licenças)\b",
        text,
        re.IGNORECASE,
    ):
        points.append(
            f"VALOR: {match.group(1).upper()} para {match.group(2)} "
            f"{match.group(3).lower()}"
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
            points.append(f"PRAZO: {action} na {weekday}")
    return points[:2]


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


CHUNK_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "pontos_chave": {
            "type": "array",
            "items": {
                "type": "string",
                "maxLength": 100,
                "pattern": (
                    "^(DECISÃO|AÇÃO|PRAZO|VALOR|PROBLEMA|DÚVIDA|"
                    "EVIDÊNCIA|INSIGHT): .+$"
                ),
            },
            "minItems": 1,
            "maxItems": 4,
        },
    },
    "required": ["pontos_chave"],
    "additionalProperties": False,
}

FINAL_LIST_SCHEMA = {
    "type": "array",
    "items": {"type": "string", "maxLength": 180},
    "maxItems": 3,
}

FINAL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "resumo_geral": {"type": "string", "maxLength": 600},
        "temas_agrupados": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "tema": {"type": "string", "maxLength": 100},
                    "pontos": FINAL_LIST_SCHEMA,
                },
                "required": ["tema", "pontos"],
                "additionalProperties": False,
            },
        },
        "problemas_identificados": FINAL_LIST_SCHEMA,
        "decisoes_tomadas": FINAL_LIST_SCHEMA,
        "duvidas_em_aberto": FINAL_LIST_SCHEMA,
        "oportunidades_insights": FINAL_LIST_SCHEMA,
        "evidencias_importantes": FINAL_LIST_SCHEMA,
        "metricas_negocio": {
            "type": "object",
            "additionalProperties": {"type": ["string", "number"]},
            "maxProperties": 4,
        },
        "acoes_recomendadas": FINAL_LIST_SCHEMA,
    },
    "required": [
        "resumo_geral", "temas_agrupados", "problemas_identificados",
        "decisoes_tomadas", "duvidas_em_aberto", "oportunidades_insights",
        "evidencias_importantes", "metricas_negocio", "acoes_recomendadas",
    ],
    "additionalProperties": False,
}


def complete_missing_fields(
    final_summary: dict[str, Any],
    chunk_summaries: list[dict],
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    properties = FINAL_SUMMARY_SCHEMA["properties"]
    missing = [
        name for name in FINAL_SUMMARY_SCHEMA["required"]
        if name not in final_summary or final_summary[name] is None
    ]
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
        min(settings.ollama_consolidation_num_predict, 384),
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


def generate_chunk_summary(
    clean_content: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    prompt = f"""Você é um especialista em análise de reuniões corporativas.
Analise somente o trecho e retorne JSON apenas com pontos_chave.
Use no máximo 4 pontos muito curtos. Prefixe cada
ponto com exatamente uma categoria entre DECISÃO, AÇÃO, PRAZO, VALOR,
PROBLEMA, DÚVIDA, EVIDÊNCIA ou INSIGHT, seguida de dois-pontos e do fato concreto.
Nunca devolva apenas nomes de categorias. Preserve nomes, números e negações.
Copie apenas ações explicitamente mencionadas; não crie novas ações. O trecho
contém fatos relevantes: extraia pelo menos um deles. Não invente fatos.

TRECHO:
{clean_content}"""
    summary = _generate_json(
        prompt,
        CHUNK_SUMMARY_SCHEMA,
        settings.ollama_chunk_think,
        settings.ollama_chunk_num_predict,
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
        if len(merged) == 4:
            break
    return {"pontos_chave": merged}


def consolidate_summaries(
    chunk_summaries: list[dict], *, client: httpx.Client | None = None
) -> dict[str, Any]:
    summaries_json = json.dumps(chunk_summaries, ensure_ascii=False)
    prompt = f"""Você é um especialista em análise de reuniões corporativas.
Consolide os resumos parciais abaixo em um único objeto JSON válido com estas chaves:
resumo_geral, temas_agrupados, problemas_identificados, decisoes_tomadas,
duvidas_em_aberto, oportunidades_insights, evidencias_importantes,
metricas_negocio e acoes_recomendadas. Remova duplicações e não invente fatos.
Os resumos parciais contêm pontos prefixados por categoria; transforme os fatos
concretos nos campos finais e descarte qualquer item que seja apenas um rótulo.

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
