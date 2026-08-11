import json

import httpx
import pytest

from src.app.core.config import settings
from src.app.services.llm_service import (
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    consolidate_summaries,
    generate_chunk_summary,
    generate_embedding,
)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_chunk_summary_uses_configured_model_and_decodes_json(monkeypatch):
    monkeypatch.setattr(settings, "model", "modelo-do-env:latest")
    monkeypatch.setattr(settings, "ollama_chunk_think", True)
    monkeypatch.setattr(settings, "ollama_chunk_num_predict", 768)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload["model"] == "modelo-do-env:latest"
        assert "não crie novas ações" in payload["prompt"].lower()
        assert "lista vazia" in payload["prompt"].lower()
        assert payload["format"]["type"] == "object"
        assert payload["format"]["additionalProperties"] is False
        assert payload["stream"] is False
        assert payload["think"] is True
        assert payload["options"]["num_predict"] == 768
        return httpx.Response(
            200,
            json={"response": json.dumps({"temas_discutidos": ["ERP"]})},
        )

    result = generate_chunk_summary("Integração com ERP", client=client_for(handler))

    assert result == {"temas_discutidos": ["ERP"]}


def test_consolidate_summaries_uses_its_own_thinking_budget(monkeypatch):
    monkeypatch.setattr(settings, "ollama_consolidation_think", True)
    monkeypatch.setattr(settings, "ollama_consolidation_num_predict", 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "Integração" in payload["prompt"]
        assert payload["think"] is True
        assert payload["options"]["num_predict"] == 1024
        return httpx.Response(
            200,
            json={"response": json.dumps({"resumo_geral": "Resumo real"})},
        )

    result = consolidate_summaries(
        [{"temas_discutidos": ["Integração"]}], client=client_for(handler)
    )

    assert result == {"resumo_geral": "Resumo real"}


def test_generate_embedding_uses_configured_model(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model", "embed-do-env")
    monkeypatch.setattr(settings, "embedding_dim", 3)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {
            "model": "embed-do-env",
            "input": "conteúdo",
        }
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    assert generate_embedding("conteúdo", client=client_for(handler)) == [0.1, 0.2, 0.3]


def test_generate_embedding_rejects_unexpected_dimension(monkeypatch):
    monkeypatch.setattr(settings, "embedding_dim", 3)
    client = client_for(
        lambda _request: httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
    )

    with pytest.raises(OllamaResponseError, match="2 dimensões; esperado 3"):
        generate_embedding("conteúdo", client=client)


def test_missing_model_error_points_to_installer():
    client = client_for(
        lambda _request: httpx.Response(
            404, json={"error": "model 'ausente' not found"}
        )
    )

    with pytest.raises(OllamaModelNotFoundError, match=r"./ia/install-model.sh"):
        generate_chunk_summary("conteúdo", client=client)


def test_invalid_generation_json_is_rejected():
    client = client_for(
        lambda _request: httpx.Response(200, json={"response": "não é json"})
    )

    with pytest.raises(OllamaResponseError, match="JSON inválido"):
        generate_chunk_summary("conteúdo", client=client)


def test_generation_retries_one_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "ollama_read_timeout_retries", 1)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            json={"response": json.dumps({"resumo_chunk": "ok"})},
        )

    result = generate_chunk_summary("conteúdo", client=client_for(handler))

    assert result["resumo_chunk"] == "ok"
    assert attempts == 2


def test_generation_reports_exhausted_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "ollama_read_timeout_retries", 1)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(OllamaError, match="timed out"):
        generate_chunk_summary("conteúdo", client=client_for(handler))

    assert attempts == 2
