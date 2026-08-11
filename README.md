# KOLIA IA Service

Serviço FastAPI responsável por analisar transcrições, dividi-las em chunks e
persistir resumos e embeddings de desenvolvimento no Postgres com pgvector.

## Executar

Na raiz do projeto:

```bash
docker compose up -d --build ia-service
```

O serviço fica disponível em `http://localhost:3000`.

## Endpoints

- `GET /health`
- `POST /analisar`
- `GET /analises/{analysis_id}`
- `GET /analises/by-meeting/{meeting_id}`
- `GET /analises/{analysis_id}/chunks`

`POST /analisar` persiste os chunks e responde imediatamente com HTTP `202` e
um `analysis_id`. O processamento pesado ocorre em fila serial para evitar
disputa pelo único slot do Ollama. Consulte `GET /analises/{analysis_id}` até
receber `DASHBOARD_READY`, `DONE`, `FAILED_ANALYSIS` ou
`DASHBOARD_READY_WITH_EMBEDDING_ERROR`.

O dashboard já pode consumir `final_summary` em `DASHBOARD_READY`. Os
embeddings continuam em segundo plano até `DONE`; falhas nessa etapa não
removem o resumo.

## Testes

```bash
docker compose run --rm --no-deps ia-service python -m pytest -q tests
```

Os resumos e embeddings são gerados pelo Ollama. O modelo de análise vem de
`OLLAMA_MODEL` e o de embedding de `EMBEDDING_MODEL`. Se algum modelo estiver
ausente, execute o instalador interativo na raiz do projeto:

```bash
./ia/install-model.sh
```

As demais configurações disponíveis estão documentadas em `.env.example`.
