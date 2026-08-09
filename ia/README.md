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

## Testes

```bash
docker compose run --rm --no-deps ia-service python -m pytest -q tests
```

O resumo e o embedding atuais são mocks determinísticos para validar o fluxo do
MVP. As configurações disponíveis estão documentadas em `.env.example`.
