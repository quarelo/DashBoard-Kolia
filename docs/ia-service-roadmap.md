# KOLIA — Estado atual e roadmap do serviço de IA

Atualizado em 2026-09-12. A versão anterior deste documento descrevia um backend
Java, o modelo `qwen3:1.7b`, um endpoint síncrono e nenhum chat. Nada disso vale
mais; o que mudou está na seção 9, fase por fase.

## 1. Objetivo

O serviço de IA recebe a transcrição de uma reunião e devolve:
- o resumo estruturado que alimenta o dashboard (13 campos);
- um índice da reunião para busca e chat.

Ele roda em FastAPI (`ia/`), usa o Ollama local e persiste tudo no schema `ai` do
PostgreSQL com pgvector.

## 2. Arquitetura atual

```text
Frontend React ──▶ Backend FastAPI (schema core)
                      │  token de serviço, Idempotency-Key
                      ▼
                   Serviço de IA FastAPI (schema ai)
                      ├── fila em memória + worker (1 análise por vez)
                      ├── Ollama: resumo por chunk, consolidação, produto, chat
                      ├── Ollama: embeddings (nomic-embed-text)
                      └── PostgreSQL + pgvector
```

O backend é dono de usuários, importação e permissões. A IA não conhece usuário:
recebe `meeting_id`, título, transcrição e até 5 campos de contexto comercial do
CSV.

## 3. Fluxo da análise

```text
POST /analisar
→ reserva a Idempotency-Key (ai.analysis_submissions)
→ sanitiza, conta tokens, fatia em chunks de 2000 tokens (overlap 120)
→ grava a análise em PROCESSING com um resumo preliminar determinístico
→ enfileira e responde 202

worker
→ ANALYZING: resume com o LLM os chunks de maior sinal, até MAX_LLM_CHUNKS (15),
  dois por vez; os demais recebem resumo determinístico
→ a cada chunk resumido, regrava o resumo parcial do card
→ consolidação por LLM, também em reunião de um chunk só
→ churn e oportunidade pela tabela de motivos; evidências conferidas contra a
  transcrição; produto escolhido só do catálogo ai.products
→ completa campos ausentes e limpa o texto do card
→ DASHBOARD_READY (resumo final)
→ EMBEDDING: passagens de 400 tokens (overlap 40), uma a uma
→ DONE: busca e chat liberados
```

| Status | Significado |
|---|---|
| `PROCESSING` | criada e na fila |
| `ANALYZING` | resumindo os chunks |
| `DASHBOARD_READY` | resumo final pronto; embeddings a seguir |
| `EMBEDDING` | gerando os embeddings |
| `DONE` | resumo e índice prontos |
| `DASHBOARD_READY_WITH_EMBEDDING_ERROR` | resumo pronto, índice falhou; chat fechado |
| `FAILED`, `FAILED_ANALYSIS` | falha, com `error_message` |

O card também informa `summary_stage` (`PRELIMINARY`, `PARTIAL`, `COMPLETE`) e
`summary_is_final`.

Ao subir, o worker retoma as análises em `PROCESSING`, `ANALYZING`,
`DASHBOARD_READY` e `EMBEDDING`, e reaproveita os chunks já resumidos. Uma reserva
de idempotência sem análise, deixada por uma falha antes da criação, não expira: a
reunião responde 409 até alguém apagar a reserva (ver
`docs/meeting-import-flow.md`).

## 4. Modelos

| Papel | Configuração | Hoje |
|---|---|---|
| Chat | `OLLAMA_MODEL` | `qwen3.5:4b-q4_K_M` |
| Resumo por chunk | `OLLAMA_CHUNK_MODEL`, `OLLAMA_CHUNK_NUM_PREDICT=384` | `qwen3.5:4b-q4_K_M` |
| Consolidação, completar campos, produto | `OLLAMA_CONSOLIDATION_MODEL`, `OLLAMA_CONSOLIDATION_NUM_PREDICT=1536` | `qwen3.5:4b-q4_K_M` |
| Embeddings | `EMBEDDING_MODEL`, `EMBEDDING_DIM=768` | `nomic-embed-text` |

- **Contexto:** 32768 tokens.
- **GPU:** entra por `docker-compose.gpu.yml`, ligado com `COMPOSE_FILE` no `.env`.
- **Thinking:** desligado nas chamadas com schema JSON. Na consolidação, ligado
  devolveu resposta vazia em 3 de 3 perfis.

A escolha dos modelos, os limites de tokens e os prompts, com as medições que os
sustentam, estão em `docs/prompts.md`.

## 5. Chat da reunião

`POST /analises/{id}/chat`. Só abre com a análise em `DONE`, e só lê a própria
reunião.

1. **Perguntas sobre o card:** perguntas que batem com um campo do resumo (produto,
   budget, dúvidas...) respondem direto do `final_summary`.
2. **Busca híbrida:** passagens por vetor e por texto (`tsvector` em português),
   fundidas por posição. Termos presentes em mais de 35% das passagens da reunião
   são descartados. Uma segunda opinião traz a passagem com o termo mais raro da
   pergunta.
3. **Resposta:** o modelo responde só com as evidências. Se ele recusar, copiar a
   pergunta ou um trecho, ou responder curto demais, há uma releitura com três
   trechos.
4. **Números:** números que não aparecem nas evidências derrubam a resposta.
5. **Citações e histórico:** as citações são recortadas em torno da resposta (350
   caracteres). A conversa fica em `ai.chat_messages` e volta ao reabrir a página.

## 6. API atual

| Rota | Uso |
|---|---|
| `GET /health` | saúde |
| `POST /analisar` | cria análise assíncrona |
| `GET /analises/{id}`, `GET /analises/by-meeting/{meeting_id}` | status, progresso, resumo |
| `GET /fila` | análises não terminadas e tempo estimado da fila |
| `GET /estimativa?analyses=&chunks_each=` | custo de um lote ainda não enviado |
| `GET /analises/{id}/estimativa` | tempo restante de uma análise |
| `POST /analises/{id}/recompletar` | pede de novo, uma vez, os campos vazios de um card pronto |
| `GET /analises/{id}/chunks` | chunks e resumos parciais |
| `POST /analises/{id}/buscar` | busca híbrida |
| `GET /analises/{id}/evidencias` | evidências por categoria |
| `GET` e `POST /analises/{id}/chat` | histórico e nova pergunta |

As estimativas vêm do histórico desta máquina. Elas usam a mediana por número de
chunks, sem uma reta única, e mudam depois de uma troca de modelo ou de hardware.

## 7. Dados persistidos

| Tabela | Conteúdo |
|---|---|
| `ai.meeting_analyses` | status, estágio do resumo, `final_summary`, contexto comercial (`source_metadata`), erro |
| `ai.meeting_chunks` | conteúdo original e limpo, tokens, resumo do chunk, embedding legado |
| `ai.chunk_passages` | passagens de ~400 tokens com embedding e `tsvector` |
| `ai.analysis_submissions` | chave de idempotência, hash do payload, análise criada |
| `ai.products` | catálogo TOTVS (302 produtos) com embedding |
| `ai.chat_messages` | conversa por análise |

As migrações vão de `0001` a `0008`, com `0007` = `chat_messages` e
`0008` = `source_metadata`.

## 8. Limitações conhecidas

Medidas nas reuniões do CSV em 2026-09-12:

- **Evidência parafraseada.** A consolidação só vê os resumos dos chunks, então o
  trecho que ela cita costuma ser a frase do resumo. O filtro contra a transcrição
  descarta esses trechos, e o card fica sem evidência: 0 evidências em 3 de 5
  reuniões. Trocar pelo trecho mais parecido da transcrição não se sustentou na
  calibração.
- **Motivos super-declarados.** Houve oportunidade 85 numa reunião de cancelamento
  e churn de 50 a 55 em reuniões de venda. A calibração com reuniões rotuladas
  segue pendente.
- **Persona.** Às vezes traz nome próprio ou marcador de anonimização
  (`[PESSOA]`, `[LOCAL]`).
- **Justificativas cortadas.** O texto para nos 240 caracteres do schema, às vezes
  no meio da palavra. Os itens de lista já voltam à última frase completa; as
  justificativas ainda não.
- **Metadado inconsistente.** Há reunião marcada como `lead` no CSV que é de
  cliente com contrato, e o contexto comercial repassa isso ao modelo.
- **Reprocessamento manual.** Uma análise que termina em erro fica ligada à
  reunião, e a carga do dataset não a reenvia.
- **Fila.** Fica em memória, numa instância só. Não há coordenação entre réplicas
  nem cancelamento.
- **Tokens.** `total_tokens` é estimativa da transcrição, não o consumo real do
  Ollama.

## 9. Roadmap

### Fase 1 — Seleção de modelo · pendente

Listar os modelos instalados, trocar o modelo ativo sem editar o `.env` e registrar
em cada análise o modelo e os limites usados. Uma análise em andamento termina com
o modelo com que começou.

### Fase 2 — Reprocessamento · parcial

- **Feito:**
  - retomada de chunks já resumidos depois de uma queda;
  - `recompletar` para campos vazios de um card pronto.
- **Pendente:**
  - reprocessar uma análise que terminou em erro;
  - refazer só uma etapa (embeddings, consolidação) ou um chunk;
  - guardar o histórico de tentativas.

### Fase 3 — Processamento assíncrono · feito

- **Feito:** `POST /analisar` responde 202, e o worker processa em segundo plano com
  retomada no startup. Há progresso por análise e estimativa de fila.
- **Pendente:** fila persistente ou distribuída e cancelamento.

### Fase 4 — Chat contextual · feito

- **Feito:** RAG com fontes, isolado por análise, com releitura, checagem de números
  e histórico persistido.
- **Pendente:** guardar em cada mensagem as fontes e o modelo usados.

### Fase 5 — Métricas e observabilidade · parcial

- **Feito:** logs com `analysis_id` e tempo por etapa, e ETA calibrado pelo histórico.
- **Pendente:**
  - persistir `eval_count` e tempos do Ollama por chamada;
  - métricas Prometheus;
  - alerta para análise travada ou taxa alta de falha.

### Fase 6 — Qualidade da análise · aberta

- **Evidência literal:** dar à consolidação trechos da transcrição, e não só
  resumos.
- **Motivos:** calibrar a declaração de motivos contra reuniões rotuladas.
- **Justificativas:** cortar na última frase completa, como já acontece nas listas.

## 10. Ordem recomendada

1. Qualidade da análise (fase 6): é o que o dashboard mostra hoje.
2. Reprocessar análise com erro (fase 2), antes da carga completa do dataset.
3. Registro de modelo e métricas por chamada (fases 1 e 5).
4. Seleção de modelo pela interface (fase 1).
5. Fila persistente e cancelamento (fase 3).
