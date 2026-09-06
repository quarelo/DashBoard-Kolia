# KOLIA

Aplicação para organizar reuniões comerciais, gerar resumos com IA e consultar
uma reunião por meio de um chatbot RAG. O ambiente de desenvolvimento roda em
contêineres separados e é orquestrado pelo Docker Compose.

O backend aceita reuniões em CSV/JSON com deduplicação persistida, versionamento
de transcrição corrigida e envio idempotente para análise. Consulte o
[fluxo de importação](docs/meeting-import-flow.md) para contratos, uso pelo
Swagger e comandos de teste. O frontend ainda usa fixtures.


## Arquitetura

Dois serviços dividem um PostgreSQL, e a fronteira entre eles é o schema: nenhum
escreve na tabela do outro.

```text
                        Navegador
                            │
                            ▼
   Frontend React/Vite :5173      (ainda lê fixtures locais)
                            │
                            ▼
   ┌──────────────────────┐   token de serviço    ┌──────────────────────┐
   │  Backend FastAPI     │ ────────────────────▶ │  Serviço de IA       │
   │  :8080 · schema core │                       │  :3000 · schema ai   │
   │                      │                       │                      │
   │  login e JWT         │                       │  fatia em chunks     │
   │  importa CSV/JSON    │                       │  resume com o LLM    │
   │  versiona reuniões   │                       │  gera embeddings     │
   │  despacha análise    │                       │  busca híbrida e chat│
   └──────────┬───────────┘                       └─────┬──────────┬─────┘
              │                                         │          │
              │                                         │          ▼
              │                                         │   Ollama :11434
              ▼                                         ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │            PostgreSQL 16 + pgvector  ·  porta 5433                 │
   │                                                                    │
   │  core.users            ai.meeting_analyses    ai.chunk_passages    │
   │  core.meeting_imports  ai.meeting_chunks      ai.analysis_submis…  │
   └────────────────────────────────────────────────────────────────────┘
```

### O caminho de uma reunião

1. **Importar** — CSV ou JSON pelo backend, com deduplicação por hash do arquivo
   e do conteúdo. Importar nunca dispara análise.
2. **Analisar** — chamada explícita por reunião. O backend resolve a transcrição
   salva, deriva uma chave de idempotência do UUID interno mais o hash do texto, e
   despacha. Clique repetido ou timeout reaproveitam a mesma análise.
3. **Resumir** — a IA fatia em blocos de ~2000 tokens, manda os de maior sinal ao
   LLM e consolida no contrato de 13 campos do dashboard.
4. **Indexar** — cada bloco é dividido em passagens de ~400 tokens, embeddadas
   individualmente no pgvector.
5. **Consultar** — busca e chat, isolados por análise, só depois que todos os
   embeddings existem.

### Decisões que explicam o desenho

- **Dois tamanhos de texto.** O bloco de ~2000 tokens existe para resumir com
  poucas chamadas ao LLM; a passagem de ~400 existe para buscar. Um vetor médio
  sobre duas mil palavras dissolve a frase que cita um preço — perguntar por
  valores devolvia cinco trechos sem nenhum `R$`.
- **Busca híbrida.** Vetorial acha o assunto e perde o fato específico; textual
  acha a palavra e perde o contexto. As duas rodam e os resultados são fundidos
  por posição (*reciprocal rank fusion*), então nenhuma precisa acertar sozinha.
- **Churn e oportunidade são aritmética.** Um catálogo fixo de motivos com pontos
  definidos pelo negócio, somados e limitados em 100. A camada de cálculo é pura e
  determinística: a mesma combinação sempre gera o mesmo score.
- **Reprocessar cria versão.** Transcrição corrigida vira uma nova versão da
  reunião, com análise própria. A anterior mantém seus chunks e citações.
- **O app não cria schema.** No startup ele confere a revisão do Alembic e recusa
  subir se estiver defasada. Cada serviço tem suas migrações e sua tabela de
  versão, no seu schema.

Os componentes:

- `frontend`: interface React, TypeScript, Vite e Tailwind CSS. **Ainda lê os JSON
  de exemplo em `src/data/`; não consome as APIs abaixo.**
- `backend`: autenticação, importação, versionamento e despacho de análise.
- `ia-service`: chunking, resumo, embeddings, busca híbrida e chat.
- `ollama`: inferência local dos modelos de geração e embedding.
- `postgres`: PostgreSQL 16 com pgvector, com os schemas `core` e `ai`.

## Requisitos

- Docker com o plugin Docker Compose;
- GNU Make;
- memória e espaço suficientes para os modelos locais do Ollama.

```bash
docker --version
docker compose version
make --version
```

## Configuração

Opcionalmente, copie as configurações padrão antes da primeira execução:

```bash
cp .env.example .env
```

Variáveis principais:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: acesso ao banco;
- `JWT_SECRET`: assinatura dos tokens do backend;
- `OLLAMA_MODEL`: modelo principal de geração;
- `OLLAMA_CHUNK_MODEL`: modelo usado nos resumos parciais;
- `OLLAMA_CONSOLIDATION_MODEL`: consolidação do resumo final;
- `EMBEDDING_MODEL` e `EMBEDDING_DIM`: embeddings usados pelo pgvector;
- `CHAT_CONTEXT_LENGTH`: janela de contexto do chatbot;
- `CHAT_SIMILARITY_THRESHOLD`: confiança mínima da evidência recuperada.

Consulte [.env.example](.env.example) para todas as opções. Não versione
segredos reais no arquivo `.env`.

## Executar

Na raiz do projeto, suba tudo com logs visíveis:

```bash
make dev
```

Para executar em segundo plano:

```bash
make dev-detached
```

Comandos úteis:

```bash
make ps       # estado dos contêineres
make logs     # acompanha os logs
make down     # encerra sem apagar banco ou modelos
```

| Serviço | Endereço |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend | `http://localhost:8080` |
| Serviço de IA | `http://localhost:3000` |
| Ollama | `http://localhost:11434` |
| PostgreSQL | `localhost:5433` |

Os volumes `postgres_data` e `ollama_data` preservam o banco e os modelos após
`make down`. Não use `docker compose down -v` se quiser manter esses dados.

## Modelos do Ollama

Na primeira instalação, baixe os modelos configurados em `.env.example`:

```bash
./ia/install-model.sh
```

Para listar os modelos disponíveis:

```bash
docker compose exec ollama ollama list
```

## API de IA

Rotas principais:

- `GET /health`: saúde do serviço;
- `POST /analisar`: inicia uma análise assíncrona;
- `GET /analises/{analysis_id}`: status, progresso e resumo;
- `GET /analises/by-meeting/{meeting_id}`: análise mais recente da reunião;
- `GET /analises/{analysis_id}/chunks`: chunks processados;
- `POST /analises/{analysis_id}/buscar`: busca semântica;
- `GET /analises/{analysis_id}/evidencias`: evidências por categoria;
- `POST /analises/{analysis_id}/chat`: conversa RAG limitada à reunião.

O resumo fica disponível em `final_summary` quando o processamento chega a
`DASHBOARD_READY`. Os embeddings seguem em segundo plano até `DONE`. O chatbot
só responde com evidências recuperadas; quando não encontra suporte suficiente,
informa que a transcrição não contém a resposta.

## Testes

Execute tudo na raiz:

```bash
make test
```

Ou separadamente:

```bash
make test-backend
make test-ia
make test-frontend
```

O workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) executa as
verificações em pushes para `main` e em pull requests.

## Estrutura

```text
backend/             API de autenticação
frontend/            aplicação React/Vite
ia/                  serviço de análise, resumo e RAG
infra/postgres/      inicialização do PostgreSQL/pgvector
docs/                especificações, planos e handoffs
docker-compose.yml   orquestração local
Makefile             comandos de desenvolvimento e testes
```

## Solução de problemas

```bash
make ps
make logs
```

Se a IA informar que um modelo não existe, execute novamente
`./ia/install-model.sh`. Se o chatbot ainda estiver processando embeddings,
acompanhe `GET /analises/{analysis_id}` até o status `DONE`.
