import json

import httpx
import pytest

from src.app.core.config import settings
from src.app.services.llm_service import (
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    consolidate_summaries,
    complete_missing_fields,
    generate_chunk_summary,
    generate_chat_answer,
    generate_embedding,
)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_chunk_summary_uses_configured_model_and_decodes_json(monkeypatch):
    monkeypatch.setattr(settings, "chunk_model", "modelo-chunk:latest")
    monkeypatch.setattr(settings, "ollama_keep_alive", "30m")
    monkeypatch.setattr(settings, "ollama_chunk_think", True)
    monkeypatch.setattr(settings, "ollama_chunk_num_predict", 768)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload["model"] == "modelo-chunk:latest"
        assert payload["keep_alive"] == "30m"
        assert "não crie novas ações" in payload["prompt"].lower()
        assert "extraia pelo menos um" in payload["prompt"].lower()
        assert "métricas de exemplo" in payload["prompt"].lower()
        assert "não use a palavra" in payload["prompt"].lower()
        assert payload["format"]["type"] == "object"
        assert payload["format"]["additionalProperties"] is False
        # Motive arrays are enum-constrained here, so scoring reads catalogue
        # codes instead of matching however the model worded the fact.
        assert set(payload["format"]["properties"]) == {
            "pontos_chave", "motivos_churn", "motivos_oportunidade"}
        assert payload["format"]["properties"]["pontos_chave"]["minItems"] == 1
        assert payload["format"]["properties"]["pontos_chave"]["items"]["pattern"] == (
            "^(PRODUTO|PERSONA|SENTIMENTO|CHURN|OPORTUNIDADE|BUDGET|"
            "GAP|PROBLEMA|FEEDBACK|DÚVIDA|AÇÃO|EVIDÊNCIA): .+$"
        )
        assert payload["stream"] is False
        assert payload["think"] is True
        assert payload["options"]["num_predict"] == 768
        return httpx.Response(
            200,
            json={"response": json.dumps({"pontos_chave": ["EVIDÊNCIA: ERP"]})},
        )

    result = generate_chunk_summary("Integração com ERP", client=client_for(handler))

    assert result["pontos_chave"] == ["EVIDÊNCIA: ERP"]


def test_consolidate_summaries_uses_its_own_thinking_budget(monkeypatch):
    monkeypatch.setattr(settings, "consolidation_model", "modelo-final:latest")
    monkeypatch.setattr(settings, "ollama_consolidation_think", True)
    monkeypatch.setattr(settings, "ollama_consolidation_num_predict", 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "modelo-final:latest"
        assert "Integração" in payload["prompt"]
        assert payload["think"] is True
        assert payload["options"]["num_predict"] == 1024
        assert payload["format"]["properties"]["oportunidade_comercial"]["maxItems"] == 3
        assert payload["format"]["properties"]["evidencias"]["maxItems"] == 24
        assert "pedido cancelado" in payload["prompt"].lower()
        assert "troca de computador" in payload["prompt"].lower()
        return httpx.Response(
            200,
            json={"response": json.dumps({"produto": ["TOTVS ERP"]})},
        )

    result = consolidate_summaries(
        [{"temas_discutidos": ["Integração"]}], client=client_for(handler)
    )

    assert result == {"produto": ["TOTVS ERP"]}


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


def test_generate_chat_answer_uses_one_short_non_thinking_request(monkeypatch):
    monkeypatch.setattr(settings, "model", "modelo-chat:latest")
    monkeypatch.setattr(settings, "chat_num_predict", 512)
    monkeypatch.setattr(settings, "chat_temperature", 0.0)
    monkeypatch.setattr(settings, "chat_context_length", 8192)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert payload == {
            "model": "modelo-chat:latest",
            "prompt": "PERGUNTA: Quantas máquinas?",
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "think": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
                "num_ctx": 8192,
            },
        }
        return httpx.Response(200, json={"response": "  Foram 27 máquinas.  "})

    answer = generate_chat_answer(
        "PERGUNTA: Quantas máquinas?", client=client_for(handler)
    )

    assert answer == "Foram 27 máquinas."
    assert len(requests) == 1


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


def test_generation_extracts_json_from_markdown_fence():
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={
                "response": '```json\n{"pontos_chave":["EVIDÊNCIA: ok"]}\n```'
            },
        )
    )

    assert generate_chunk_summary("conteúdo", client=client)["pontos_chave"] == [
        "EVIDÊNCIA: ok"
    ]


def test_generation_repairs_invalid_json_once(monkeypatch):
    monkeypatch.setattr(settings, "ollama_json_repair_enabled", True)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raw = (
            "{invalid"
            if calls == 1
            else '{"pontos_chave":["EVIDÊNCIA: reparado"]}'
        )
        return httpx.Response(200, json={"response": raw})

    result = generate_chunk_summary("conteúdo", client=client_for(handler))

    assert result["pontos_chave"] == ["EVIDÊNCIA: reparado"]
    assert calls == 2


def test_generation_retries_truncated_output_with_larger_budget(monkeypatch):
    monkeypatch.setattr(settings, "ollama_chunk_num_predict", 192)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["options"]["num_predict"])
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "response": '{"pontos_chave":["AÇÃO: resposta cortada',
                    "done_reason": "length",
                    "eval_count": 192,
                },
            )
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {"pontos_chave": ["AÇÃO: enviar proposta"]}
                )
            },
        )

    result = generate_chunk_summary("conteúdo", client=client_for(handler))

    assert result["pontos_chave"] == ["AÇÃO: enviar proposta"]
    assert calls == [192, 384]


def test_chunk_summary_normalizes_and_preserves_commercial_categories():
    response = {
        "pontos_chave": [
            "AÇÃO: enviar proposta",
            "DÚVIDAS: qual é o prazo?",
            "BUDGET: R$ 40 mil",
            "PRODUTO: TOTVS CRM",
            "OPORTUNIDADE: ampliar licenças",
            "GAP: integração ausente",
            "FEEDBACK: item excedente",
        ]
    }
    client = client_for(
        lambda _request: httpx.Response(
            200, json={"response": json.dumps(response, ensure_ascii=False)}
        )
    )

    result = generate_chunk_summary("conteúdo", client=client)

    assert result["pontos_chave"] == [
        "AÇÃO: enviar proposta",
        "DÚVIDA: qual é o prazo?",
        "BUDGET: R$ 40 mil",
        "PRODUTO: TOTVS CRM",
        "OPORTUNIDADE: ampliar licenças",
        "GAP: integração ausente",
        "FEEDBACK: item excedente",
    ]


def test_chunk_summary_salvages_only_complete_items_from_truncated_json(
    monkeypatch,
):
    monkeypatch.setattr(settings, "ollama_json_repair_enabled", False)
    raw = (
        '{"pontos_chave":["AÇÃO: enviar proposta",'
        '"BUDGET: R$ 40 mil","PRODUTO: TOTVS CRM",'
        '"PROBLEMA: integração ausente","DÚVIDA: item cortado'
    )
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={"response": raw, "done_reason": "stop", "eval_count": 150},
        )
    )

    result = generate_chunk_summary("conteúdo", client=client)

    assert result["pontos_chave"] == [
        "AÇÃO: enviar proposta",
        "BUDGET: R$ 40 mil",
        "PRODUTO: TOTVS CRM",
        "PROBLEMA: integração ausente",
    ]


def test_chunk_summary_preserves_explicit_quantity_and_dated_commitment():
    model_response = {
        "pontos_chave": [
            "EVIDÊNCIA: discussão sobre licenças",
            "AÇÃO: avaliar o cenário",
        ]
    }
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={"response": json.dumps(model_response, ensure_ascii=False)},
        )
    )
    text = (
        "Vou fazer de CRM para 25 pessoas e depois ajustar. "
        "Eu vou montar esses planos [ L67 ] : de viagem [ L65 ] : "
        "na segunda-feira."
    )

    result = generate_chunk_summary(text, client=client)

    assert "OPORTUNIDADE: CRM para 25 pessoas" in result["pontos_chave"]
    assert (
        "AÇÃO: montar esses planos de viagem na segunda-feira"
        in result["pontos_chave"]
    )


def test_chunk_summary_recovers_explicit_commercial_signals_omitted_by_model():
    client = client_for(
        lambda _request: httpx.Response(
            200,
            json={"response": json.dumps({
                "pontos_chave": ["EVIDÊNCIA: conversa comercial"]
            })},
        )
    )
    text = (
        "[CLIENTE - Gerente de TI]: Usamos o TOTVS ERP, mas estamos "
        "insatisfeitos com a lentidão e podemos cancelar se o problema não "
        "for resolvido. Precisamos integrar WhatsApp, recurso que não "
        "encontramos hoje. Temos budget de R$ 50 mil e interesse em comprar "
        "TOTVS CRM para 25 vendedores. Qual é o prazo de implantação?"
    )

    result = generate_chunk_summary(text, client=client)
    serialized = "\n".join(result["pontos_chave"])

    for expected in (
        "PRODUTO: TOTVS ERP",
        "PERSONA: Gerente de TI",
        "SENTIMENTO: insatisfeitos com a lentidão",
        "CHURN: podemos cancelar se o problema não for resolvido",
        "GAP: integrar WhatsApp, recurso que não encontramos hoje",
        "FEEDBACK: insatisfeitos com a lentidão",
        "BUDGET: R$ 50 mil",
        "DÚVIDA: Qual é o prazo de implantação?",
        "OPORTUNIDADE: CRM para 25 vendedores",
    ):
        assert expected in serialized


def test_complete_missing_fields_requests_only_absent_fields(monkeypatch):
    monkeypatch.setattr(settings, "consolidation_model", "modelo-final")
    partial = {
        "produto": ["TOTVS ERP"],
        "persona": ["Gerente de TI"],
        "recomendacao_acao": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert set(payload["format"]["properties"]) == {
            "sentimento", "risco_churn", "oportunidade_comercial",
            "score_oportunidade", "budget", "gap_produto",
            "problemas_identificados", "feedback_produto", "evidencias",
            "recomendacao_acao", "duvidas_em_aberto",
        }
        return httpx.Response(
            200,
            json={"response": json.dumps({
                "sentimento": {"classificacao": "neutro", "justificativa": "Sem sinal forte"},
                "risco_churn": {"score": 0, "justificativa": "Sem sinal"},
                "oportunidade_comercial": [],
                "score_oportunidade": {"score": 0, "justificativa": "Sem sinal"},
                "budget": {"identificado": False, "valor": "", "contexto": "Não identificado"},
                "gap_produto": [],
                "problemas_identificados": [],
                "duvidas_em_aberto": [],
                "feedback_produto": [],
                "evidencias": [],
                "recomendacao_acao": ["Enviar proposta"],
            })},
        )

    result = complete_missing_fields(
        partial,
        [{"pontos_chave": ["AÇÃO: Enviar proposta"]}],
        client=client_for(handler),
    )

    assert result["produto"] == ["TOTVS ERP"]
    assert result["persona"] == ["Gerente de TI"]
    assert result["recomendacao_acao"] == ["Enviar proposta"]


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
            json={
                "response": json.dumps(
                    {"pontos_chave": ["EVIDÊNCIA: ok"]}
                )
            },
        )

    result = generate_chunk_summary("conteúdo", client=client_for(handler))

    assert result["pontos_chave"] == ["EVIDÊNCIA: ok"]
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
