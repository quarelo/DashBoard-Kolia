# KOLIA

Aplicação para organizar reuniões comerciais da TOTVS. Ela importa transcrições,
gera com IA um resumo estruturado de cada reunião (produto, persona, sentimento,
risco de churn, oportunidade, dúvidas em aberto), mostra tudo num dashboard e
responde perguntas sobre uma reunião por um chat RAG. Os cinco serviços rodam em
contêineres, orquestrados pelo Docker Compose.

O backend aceita reuniões em CSV/JSON com deduplicação persistida, versionamento
de transcrição corrigida e envio idempotente para análise; o
[fluxo de importação](docs/meeting-import-flow.md) tem os contratos. O frontend
consome as APIs do backend: login, dashboard executivo, lista e detalhe das
reuniões, exclusão e chat.

## Arquitetura

Dois serviços dividem um PostgreSQL, e a fronteira entre eles é o schema: `core` é
do backend, `ai` é da IA. A única exceção é excluir uma reunião, explicada no
[CLAUDE.md](CLAUDE.md).

```text
Navegador
  └─ Frontend React/Vite :5173 ── login, dashboard, reuniões, chat
       └─ Backend FastAPI :8080 (schema core)
            ├─ login e JWT
            ├─ importa e versiona CSV/JSON
            ├─ despacha análise para a IA ──── token de serviço ───┐
            ├─ lê as análises para o dashboard                      │
            └─ exclui reunião (core + ai, uma transação)            │
                                                                    ▼
                                         Serviço de IA FastAPI :3000 (schema ai)
                                           ├─ fatia em chunks e resume com o LLM
                                           ├─ confere produto contra o catálogo
                                           ├─ gera embeddings das passagens
                                           └─ busca híbrida e chat
                                                └─ Ollama :11434 (GPU)

PostgreSQL 16 + pgvector :5433
  core.users · core.meeting_imports · core.meetings
  ai.meeting_analyses · ai.meeting_chunks · ai.chunk_passages
  ai.analysis_submissions · ai.products · ai.chat_conversations · ai.chat_messages
```

### O caminho de uma reunião

1. **Importar.** CSV ou JSON pelo backend, com deduplicação por hash do arquivo e
   do conteúdo. Importar nunca dispara análise.
2. **Analisar.** Chamada explícita por reunião. O backend deriva uma chave de
   idempotência do UUID interno mais o hash do texto e despacha para a IA, que
   processa uma análise por vez. Clique repetido ou timeout reaproveitam a mesma
   análise.
3. **Resumir.** A IA fatia em blocos de ~2000 tokens e o LLM resume cada um.
   - Uma consolidação por LLM monta os 13 campos do dashboard, também em reunião de
     um bloco só.
   - Churn e oportunidade são recalculados pela tabela de motivos.
   - O produto sai do catálogo `ai.products`.
   - Status `DASHBOARD_READY`.
4. **Indexar.** Cada bloco vira passagens de ~400 tokens, embeddadas uma a uma.
   Status `DONE`.
5. **Consultar.** O dashboard lê `ai.meeting_analyses` direto do banco. O chat só
   abre com `DONE`. Cada reunião pode ter várias conversas, guardadas em
   `ai.chat_conversations` e `ai.chat_messages`.

### Decisões que explicam o desenho

- **Dois tamanhos de texto.** O bloco de ~2000 tokens existe para resumir com
  poucas chamadas ao LLM; a passagem de ~400 existe para buscar. Um vetor médio
  sobre duas mil palavras dissolve a frase que cita um preço: perguntar por
  valores devolvia cinco trechos sem nenhum `R$`.
- **Busca híbrida.** Vetorial acha o assunto e perde o fato específico; textual
  acha a palavra e perde o contexto. As duas rodam e os resultados são fundidos
  por posição (*reciprocal rank fusion*), então nenhuma precisa acertar sozinha.
- **Churn e oportunidade são aritmética.** Um catálogo fixo de motivos com pontos
  definidos pelo negócio, somados e limitados em 100. O modelo declara os códigos;
  a mesma combinação de códigos sempre gera o mesmo score.
- **Produto só do catálogo.** O modelo escolhe entre nomes que existem em
  `ai.products`, nunca escreve um nome livre
  ([detalhes](docs/product-catalog-grounding.md)).
- **Reprocessar cria versão.** Transcrição corrigida vira uma nova versão da
  reunião, com análise própria. A anterior mantém seus chunks e citações.
- **O app não cria schema.** Cada serviço tem suas migrações Alembic e sua tabela
  de versão, no seu schema. O container migra antes de subir.

## Requisitos

- Docker com o plugin Docker Compose;
- GNU Make;
- memória e espaço para os modelos locais do Ollama. Com GPU NVIDIA, o runtime
  NVIDIA do Docker.

## Configuração

Existe um `.env`, na raiz. Copie o exemplo antes da primeira execução:

```bash
cp .env.example .env
```

Variáveis principais:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` e `DATABASE_URL`: acesso ao
  banco;
- `JWT_SECRET`: assinatura dos tokens, igual nos dois serviços;
- `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml`: liga a GPU no Ollama.
  Sem ela, o Ollama roda em CPU sem avisar;
- `OLLAMA_MODEL`, `OLLAMA_CHUNK_MODEL`, `OLLAMA_CONSOLIDATION_MODEL`: hoje os três
  em `qwen3.5:4b-q4_K_M` ([por quê](docs/prompts.md));
- `EMBEDDING_MODEL` e `EMBEDDING_DIM`: `nomic-embed-text`, 768;
- `OLLAMA_CONTEXT_LENGTH` e `CHAT_CONTEXT_LENGTH`: janela de contexto, 32768;
- `FAST_DETERMINISTIC_CONSOLIDATION=false` e `TRUST_DECLARED_MOTIVES=true`:
  consolidação por LLM e score pelos códigos que o modelo declara;
- `KOLIA_EMAIL` e `KOLIA_PASSWORD`: conta usada pelo `make reunioes`.

Consulte [.env.example](.env.example) para todas as opções. O `.env` não é
versionado; não coloque segredos no `.env.example`.

## Executar

Os cinco serviços sobem juntos, pelo Compose. **Não rode nenhum deles no host**,
nem "só a IA", nem "só o backend". Os serviços se acham pelo nome
(`ia-service`, `ollama`, `postgres`), e esse nome só resolve dentro de
`kolia-network`. Com a IA no host e o resto em container, o backend não a encontra
e o chat devolve `503 IA_UNAVAILABLE` em toda mensagem.

```bash
make dev            # sobe tudo com logs visíveis
make dev-detached   # em segundo plano
make ps             # estado dos contêineres
make logs           # acompanha os logs
make down           # encerra sem apagar banco ou modelos
```

| Serviço | Endereço |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend (Swagger em `/docs`) | `http://localhost:8080` |
| Serviço de IA | `http://localhost:3000` |
| Ollama | `http://localhost:11434` |
| PostgreSQL | `localhost:5433` |

`./backend` e `./frontend` são montados com reload. `./ia` não é: depois de editar
a IA, rode `docker compose up -d --build ia-service`.

Os volumes `postgres_data` e `ollama_data` preservam o banco e os modelos após
`make down`. Não use `docker compose down -v` se quiser manter esses dados.

### Carregar o dataset

O `transcricoes_TOTVS.csv` (1.044 reuniões) fica na raiz e não é versionado. Com os
serviços de pé:

```bash
make reunioes-plano   # só divide e valida o CSV, sem login nem escrita
make reunioes LIMIT=5 # ensaio: importa tudo e analisa 5
make reunioes         # todas
```

O script importa o CSV em partes, informa quantas reuniões desse CSV vão ser
analisadas e analisa uma por vez. Reuniões de outros imports da mesma conta ficam
de fora. A cada uma, mostra o tempo médio e quanto falta. Pode
interromper e rodar de novo: as partes já importadas e as reuniões já analisadas
são puladas. As 1.044 levam uns 2 a 3 dias numa GTX 1070 Ti. Detalhes no
[fluxo de importação](docs/meeting-import-flow.md#carga-do-csv-inteiro).

## Modelos do Ollama

Na primeira instalação, baixe os modelos configurados:

```bash
./ia/install-model.sh
docker compose exec ollama ollama list
docker compose exec ollama nvidia-smi   # confirma que a GPU está visível
```

## APIs

### Backend (`:8080`)

| Rota | Uso |
| --- | --- |
| `POST /register`, `POST /login`, `GET /me` | Conta e sessão (JWT) |
| `POST /api/imports`, `GET /api/imports/{id}` | Importar CSV/JSON e consultar o comprovante |
| `GET /api/meetings`, `GET /api/meetings/filters` | Reuniões do usuário e valores para filtro |
| `GET /api/meetings/{id}`, `GET /api/meetings/{id}/versions` | Detalhe e histórico de versões |
| `POST` e `GET /api/meetings/{id}/analysis` | Iniciar e acompanhar a análise |
| `GET /api/dashboard/overview`, `GET /api/dashboard/executive` | Números agregados, com filtros de UF, segmento, unidade, formato, CNAE e data |
| `GET /api/dashboard/meetings`, `GET /api/dashboard/meetings/{analysis_id}` | Lista e detalhe das análises |
| `DELETE /api/dashboard/meetings/{analysis_id}` | Excluir reunião e análise |
| `GET /api/dashboard/meetings/{analysis_id}/chat/conversations` | Conversas da reunião, a mais recente primeiro |
| `GET /api/dashboard/meetings/{analysis_id}/chat/conversations/{id}` | Mensagens de uma conversa |
| `POST /api/dashboard/meetings/{analysis_id}/chat` | Nova pergunta; sem `conversation_id`, começa uma conversa |

### Serviço de IA (`:3000`, token de serviço)

| Rota | Uso |
| --- | --- |
| `GET /health` | Saúde do serviço |
| `POST /analisar` | Inicia uma análise assíncrona (`Idempotency-Key` opcional) |
| `GET /analises/{id}`, `GET /analises/by-meeting/{meeting_id}` | Status, progresso e resumo |
| `GET /fila`, `GET /estimativa`, `GET /analises/{id}/estimativa` | Fila e estimativas de tempo |
| `POST /analises/{id}/recompletar` | Pede de novo os campos que ficaram vazios |
| `GET /analises/{id}/chunks` | Chunks e resumos parciais |
| `POST /analises/{id}/buscar`, `GET /analises/{id}/evidencias` | Busca híbrida e evidências por categoria |
| `GET /analises/{id}/conversas`, `GET /analises/{id}/conversas/{conversation_id}` | Conversas da reunião e mensagens de uma delas |
| `POST /analises/{id}/chat` | Pergunta RAG limitada à reunião; sem `conversation_id`, começa uma conversa |

O resumo fica em `final_summary` a partir de `DASHBOARD_READY`; os embeddings seguem
até `DONE`. O chat só responde com evidência recuperada. Sem suporte suficiente,
informa que a transcrição não contém a resposta.

## Testes

```bash
make test            # backend (compileall), IA (pytest no container) e frontend (lint + build)
make test-backend
make test-ia
make test-frontend
```

`make test-ia` usa o container em execução: depois de editar `ia/`, reconstrua a
imagem antes. O [CLAUDE.md](CLAUDE.md#testes) mostra como rodar a suíte da IA como a
CI e os testes de integração do backend, que pedem um banco descartável. O
workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) roda em pushes para
`main` e em pull requests.

## Estrutura

```text
backend/                 API: login, importação, dashboard, exclusão; scripts/ (carga do CSV, superusuário)
frontend/                aplicação React/Vite
ia/                      serviço de análise, resumo, catálogo de produtos (scraper/) e RAG
docs/                    documentação viva; docs/superpowers/ e docs/handoff-* são registros datados
context/                 planejamento inicial da infraestrutura
docker-compose.yml       orquestração local
docker-compose.gpu.yml   reserva de GPU do Ollama
Makefile                 desenvolvimento, testes e carga do dataset
```

## Solução de problemas

- **`ia-service` reiniciando com `Can't locate revision`.** A imagem não conhece a
  migração em que o banco está. Rode `docker compose up -d --build ia-service`. Se
  continuar, confira em `ia/migrations/versions` se há duas revisões com o mesmo
  número.
- **Chat devolve `503 IA_UNAVAILABLE`.** O `ia-service` está fora do ar ou fora do
  Compose. Veja em `make ps` e `docker compose logs ia-service`.
- **Análise lenta.** Confirme a GPU com `docker compose exec ollama nvidia-smi` e o
  `COMPOSE_FILE` no `.env`.
- **`409 ANALYSIS_NOT_READY` numa reunião sem análise.** Ficou uma reserva presa em
  `ai.analysis_submissions`. Veja o
  [fluxo de importação](docs/meeting-import-flow.md#persistência-e-retomada).
- **Modelo não existe.** Rode `./ia/install-model.sh` de novo.
