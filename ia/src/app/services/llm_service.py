import json
from typing import Any

import httpx

from src.app.core.config import settings


class OllamaError(RuntimeError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    client: httpx.Client | None,
    timeout: float,
) -> dict[str, Any]:
    try:
        if client is None:
            response = httpx.post(url, json=payload, timeout=timeout)
        else:
            response = client.post(url, json=payload, timeout=timeout)
    except httpx.HTTPError as error:
        raise OllamaError(f"Não foi possível acessar o Ollama: {error}") from error

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
    prompt: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    data = _post_json(
        settings.ollama_generate_url,
        {
            "model": settings.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 2048},
        },
        client=client,
        timeout=180,
    )
    raw_response = data.get("response")
    if not isinstance(raw_response, str):
        raise OllamaResponseError("Resposta do Ollama não contém o campo textual 'response'.")
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise OllamaResponseError("O modelo retornou JSON inválido para a análise.") from error
    if not isinstance(parsed, dict):
        raise OllamaResponseError("O JSON da análise precisa ser um objeto.")
    return parsed


def generate_chunk_summary(
    clean_content: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    prompt = f"""Você é um especialista em análise de reuniões corporativas.
Analise somente o trecho fornecido e retorne um objeto JSON válido com estas chaves:
temas_discutidos, problemas_identificados, decisoes_tomadas, duvidas_em_aberto,
oportunidades_insights, evidencias_importantes e metricas_negocio.
Use listas para as categorias. metricas_negocio deve ser um objeto. Não invente fatos.

TRECHO:
{clean_content}"""
    return _generate_json(prompt, client=client)


def consolidate_summaries(
    chunk_summaries: list[dict], *, client: httpx.Client | None = None
) -> dict[str, Any]:
    summaries_json = json.dumps(chunk_summaries, ensure_ascii=False)
    prompt = f"""Você é um especialista em análise de reuniões corporativas.
Consolide os resumos parciais abaixo em um único objeto JSON válido com estas chaves:
resumo_geral, temas_agrupados, problemas_identificados, decisoes_tomadas,
duvidas_em_aberto, oportunidades_insights, evidencias_importantes,
metricas_negocio e acoes_recomendadas. Remova duplicações e não invente fatos.

RESUMOS PARCIAIS:
{summaries_json}"""
    return _generate_json(prompt, client=client)


def generate_embedding(
    text: str, *, client: httpx.Client | None = None
) -> list[float]:
    data = _post_json(
        settings.ollama_embed_url,
        {"model": settings.embedding_model, "input": text},
        client=client,
        timeout=120,
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
