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

O script `ia/tests/test_analisar.py` contém a transcrição manual de referência e
não é coletado pelo pytest. A suíte automatizada pode ser executada com:

```bash
docker compose run --rm --no-deps ia-service python -m pytest -q
```

Para executar a variante local otimizada, inicie o Ollama e instale o modelo
`qwen3:1.7b`:

```bash
docker compose run --rm ia-service python -m scripts.benchmark_analysis \
  --input tests/test_analisar.py \
  --variants fast-retention-05 fast-retention-10 \
  --output logs/benchmark.json
```

O relatório mede o caminho crítico até a consolidação final; embeddings ficam
fora da meta de cinco minutos.

Na máquina de referência sem GPU, o tokenizer real transforma a amostra de
40.008 tokens aproximados em cerca de 55 mil tokens do Qwen. O benchmark deve
ser usado para confirmar a capacidade do hardware antes de prometer cinco
minutos; essa meta normalmente exige GPU ou inferência externa.

O modo padrão ultrarrápido usa `FAST_TRANSCRIPTION_RETENTION_RATIO=0.05` e
consolidação determinística. No benchmark de referência ele concluiu 40.008
tokens aproximados em 85,05 segundos. Para preservar mais conteúdo, use `0.10`;
a mesma amostra concluiu em 180,15 segundos. Campos obrigatórios realmente
ausentes são solicitados isoladamente ao modelo, sem refazer campos existentes.

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
