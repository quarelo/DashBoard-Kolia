# KOLIA

Aplicação para organizar reuniões comerciais, gerar resumos com IA e consultar
uma reunião por meio de um chatbot RAG. O ambiente de desenvolvimento roda em
contêineres separados e é orquestrado pelo Docker Compose.

## Arquitetura

```text
Navegador
   │
   ▼
Frontend React/Vite :5173
   │
   ▼
Backend FastAPI :8080

Serviço de IA FastAPI :3000
   │              │
   ▼              ▼
Ollama :11434   PostgreSQL + pgvector :5433
```

Os componentes têm responsabilidades separadas:

- `frontend`: interface React, TypeScript, Vite e Tailwind CSS.
- `backend`: API FastAPI de autenticação, usuários e JWT.
- `ia-service`: processamento de transcrições, resumos, embeddings, busca
  semântica e chatbot RAG.
- `ollama`: inferência local dos modelos de geração e embedding.
- `postgres`: PostgreSQL 16 com pgvector. Armazena usuários, análises, chunks,
  resumos e vetores.

O frontend atual ainda contém dados simulados em alguns fluxos. A API de IA já
oferece resumo e chat por reunião, mas a integração completa deve passar pelo
backend antes do uso em produção.

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
