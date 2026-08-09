# KOLIA — Estado Atual e Roadmap do Serviço de IA

## 1. Objetivo

Este documento registra o funcionamento atual do serviço de IA do KOLIA e
organiza os próximos passos planejados.

O serviço recebe a transcrição de uma reunião, sanitiza o conteúdo, divide o
texto em chunks, gera uma análise estruturada com Ollama, cria embeddings e
persiste os resultados no PostgreSQL com pgvector.

As funcionalidades descritas na seção **Roadmap futuro** ainda não estão
implementadas. Elas representam a direção recomendada para a evolução do
produto.

---

## 2. Arquitetura atual

```text
Frontend
   ↓
Backend Java Spring Boot
   ↓
Serviço de IA FastAPI
   ├── sanitização e chunking
   ├── Ollama — análise estruturada
   └── Ollama — embeddings
   ↓
PostgreSQL + pgvector
```

### Responsabilidades

O backend principal será responsável por usuários, autenticação, permissões,
reuniões e regras de negócio.

O serviço FastAPI é responsável por:

- receber a transcrição;
- sanitizar o texto;
- estimar a quantidade de tokens;
- dividir transcrições grandes em chunks;
- analisar cada chunk com um modelo do Ollama;
- gerar embeddings com um modelo específico;
- consolidar análises de múltiplos chunks;
- persistir análises e chunks;
- disponibilizar os resultados por API.

---

## 3. Fluxo atual da análise

```text
transcrição original
→ sanitização global
→ contagem aproximada de tokens
→ divisão em chunks
→ limpeza individual de cada chunk
→ análise estruturada pelo Ollama
→ geração do embedding
→ persistência do chunk
→ consolidação, quando houver mais de um chunk
→ persistência da análise final
```

### Sanitização

A sanitização ocorre antes de qualquer conteúdo ser enviado ao modelo.

Atualmente ela:

- remove bytes nulos;
- normaliza espaços e quebras de linha;
- remove expressões simples de conversa introdutória;
- preserva separadamente o conteúdo original e o conteúdo limpo.

Essa etapa pode ser aprimorada posteriormente sem alterar a integração com o
Ollama.

### Chunk único

Quando a reunião gera apenas um chunk, a análise final é construída diretamente
a partir da análise estruturada desse chunk.

Não é feita uma segunda chamada de consolidação. Isso:

- preserva decisões e problemas já extraídos;
- evita contradições introduzidas por uma segunda interpretação;
- reduz o tempo de resposta.

### Múltiplos chunks

Quando existem dois ou mais chunks, o modelo analisa cada parte separadamente.
Depois, uma chamada adicional consolida os resumos parciais em uma visão final
da reunião.

---

## 4. Modelos

O fluxo utiliza dois modelos independentes.

### Modelo de análise

Responsável por resumos, decisões, problemas, dúvidas, evidências, métricas e
ações explicitamente mencionadas.

Configurado no `.env`:

```env
OLLAMA_MODEL=qwen3:1.7b
```

O Docker Compose envia esse valor ao FastAPI como `MODEL`. O nome do modelo não
fica fixo no código Python.

### Modelo de embedding

Responsável por transformar o conteúdo sanitizado em um vetor armazenado no
pgvector.

```env
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

A dimensão configurada precisa corresponder exatamente à dimensão retornada
pelo modelo.

### Instalação

O instalador verifica os modelos definidos no ambiente:

```bash
./ia/install-model.sh
```

Quando um modelo não está instalado, o operador pode:

1. baixar o modelo configurado;
2. trocar o modelo no `.env`;
3. cancelar a operação.

Também é possível instalar diretamente:

```bash
docker compose exec ollama ollama pull qwen3:1.7b
docker compose exec ollama ollama pull nomic-embed-text
```

Depois de alterar variáveis do serviço, é necessário recriar o container:

```bash
docker compose up -d --force-recreate ia-service
```

---

## 5. Thinking e limites de geração

O thinking e o orçamento de saída são configurados separadamente por etapa:

```env
OLLAMA_CHUNK_THINK=true
OLLAMA_CHUNK_NUM_PREDICT=768

OLLAMA_CONSOLIDATION_THINK=true
OLLAMA_CONSOLIDATION_NUM_PREDICT=1024
```

Essa separação permite equilibrar precisão, tempo e consumo de recursos.

- O thinking do chunk influencia a extração inicial.
- O thinking da consolidação só é utilizado quando há vários chunks.
- `NUM_PREDICT` limita a quantidade máxima de tokens gerados.
- A janela de contexto do modelo não representa a quantidade efetivamente
  utilizada em toda requisição.

O campo `total_tokens` atual representa apenas uma estimativa dos tokens da
transcrição. Ele não inclui prompt, schema, thinking ou tokens de saída.

---

## 6. Contrato atual da API

### Criar análise

```http
POST /analisar
```

Exemplo:

```json
{
  "meeting_id": "11111111-1111-1111-1111-111111111111",
  "user_id": "22222222-2222-2222-2222-222222222222",
  "title": "Reunião teste",
  "transcription": "Cliente comentou dificuldade na integração com ERP."
}
```

### Consultar análise

```http
GET /analises/{analysis_id}
GET /analises/by-meeting/{meeting_id}
```

### Consultar chunks

```http
GET /analises/{analysis_id}/chunks
```

### Health check

```http
GET /health
```

---

## 7. Dados persistidos

### `ai.meeting_analyses`

Armazena:

- identificadores externos da reunião e do usuário;
- título;
- status;
- quantidade estimada de tokens;
- quantidade de chunks;
- análise final;
- mensagem de erro;
- datas de criação e atualização.

### `ai.meeting_chunks`

Armazena:

- índice do chunk;
- conteúdo original;
- conteúdo sanitizado;
- quantidade estimada de tokens;
- análise estruturada;
- embedding;
- referência à análise principal.

---

## 8. Estados e erros atuais

Estados utilizados:

```text
PROCESSING
DONE
FAILED
```

Quando ocorre uma falha:

- a análise é marcada como `FAILED`;
- `error_message` recebe uma descrição útil;
- tokens e quantidade de chunks calculados antes da falha são preservados;
- não existe fallback silencioso para dados mockados.

Os logs registram tempos separados para:

- análise de cada chunk;
- geração de embedding;
- consolidação;
- falhas com stack trace.

---

## 9. Limitações conhecidas

- O endpoint ainda é síncrono e mantém a conexão aberta durante todo o
  processamento.
- `total_tokens` não representa o consumo real do Ollama.
- A sanitização ainda usa regras simples.
- Não existe retry automático por etapa.
- Uma falha em embedding pode interromper toda a análise.
- Não existe seleção de modelo pela interface.
- Não existe reprocessamento parcial.
- Não existe chatbot contextual da reunião.
- Modelos pequenos podem cumprir o schema, mas ainda produzir análises pouco
  precisas ou semanticamente inconsistentes.

---

# 10. Roadmap futuro

## Fase 1 — Seleção e troca de modelo

### Objetivo

Permitir que uma pessoa autorizada escolha o modelo usado na análise sem editar
arquivos manualmente.

### Funcionalidades planejadas

- listar modelos instalados no Ollama;
- exibir o modelo ativo;
- selecionar outro modelo instalado;
- solicitar download de um modelo permitido;
- validar se o modelo está disponível antes do processamento;
- mostrar tamanho, finalidade e status do download;
- manter modelos de análise e embedding separados;
- registrar qual modelo e quais configurações foram usados em cada análise.

### API sugerida

```http
GET  /models
GET  /models/active
POST /models/pull
PUT  /models/active
```

Exemplo de troca:

```json
{
  "purpose": "analysis",
  "model": "qwen3:4b"
}
```

### Regras recomendadas

- somente administradores podem trocar ou baixar modelos;
- uma análise em andamento continua usando o modelo com que começou;
- o modelo utilizado deve ser salvo junto ao resultado;
- trocar o modelo não reprocessa reuniões antigas automaticamente;
- modelos incompatíveis com embeddings devem ser recusados nessa finalidade.

### Critérios de aceite

- usuário autorizado consegue listar e selecionar modelos;
- modelo inexistente gera orientação clara de instalação;
- análises registram modelo, thinking e limites utilizados;
- troca não afeta análises já iniciadas.

---

## Fase 2 — Reprocessamento total e parcial

### Objetivo

Permitir corrigir apenas a etapa que falhou ou ficou incompleta, sem repetir
trabalho válido desnecessariamente.

### Estados por etapa

Cada análise deverá acompanhar separadamente:

```text
SANITIZATION_PENDING
SANITIZATION_DONE
CHUNKING_PENDING
CHUNKING_DONE
SUMMARY_PENDING
SUMMARY_DONE
EMBEDDING_PENDING
EMBEDDING_DONE
CONSOLIDATION_PENDING
CONSOLIDATION_DONE
FAILED
```

Cada chunk também deverá guardar status próprio de resumo e embedding.

### Modos de reprocessamento

#### Reprocessar tudo

Refaz sanitização, chunks, análises, embeddings e consolidação.

```http
POST /analises/{analysis_id}/reprocess
```

```json
{
  "mode": "full"
}
```

#### Reprocessar somente itens ausentes

Identifica etapas incompletas e executa apenas o necessário.

```json
{
  "mode": "missing"
}
```

Exemplos:

- resumo existente e embedding ausente: gerar somente embedding;
- chunks completos e consolidação ausente: consolidar novamente;
- apenas um chunk com erro: reprocessar esse chunk e consolidar;
- resultado criado com modelo antigo: permitir reprocessar com o modelo atual.

#### Reprocessar etapa específica

```json
{
  "mode": "stage",
  "stage": "embedding"
}
```

#### Reprocessar chunk específico

```http
POST /analises/{analysis_id}/chunks/{chunk_id}/reprocess
```

### Regras recomendadas

- operações devem ser idempotentes;
- dados válidos não devem ser apagados antes do novo resultado estar pronto;
- manter histórico de tentativas e erros;
- registrar modelo e configuração de cada tentativa;
- limitar quantidade de retries automáticos;
- permitir retry manual depois do limite;
- impedir dois reprocessamentos simultâneos da mesma análise.

### Critérios de aceite

- partes válidas permanecem disponíveis durante o retry;
- usuário consegue identificar exatamente a etapa que falhou;
- modo `missing` não repete etapas concluídas;
- erros e tentativas ficam auditáveis;
- resultado final é recalculado quando algum chunk muda.

---

## Fase 3 — Processamento assíncrono

### Objetivo

Evitar que o cliente mantenha uma requisição HTTP aberta por até um minuto ou
mais.

### Fluxo sugerido

```text
POST /analisar
→ cria análise com status QUEUED
→ retorna analysis_id imediatamente
→ worker processa em segundo plano
→ frontend consulta status ou recebe evento
```

Resposta inicial sugerida:

```json
{
  "analysis_id": "uuid",
  "status": "QUEUED"
}
```

Consulta:

```http
GET /analises/{analysis_id}/status
```

Evoluções possíveis:

- worker FastAPI separado;
- Redis com Celery, RQ ou Dramatiq;
- fila baseada no próprio PostgreSQL para o primeiro MVP;
- Server-Sent Events ou WebSocket para progresso;
- cancelamento de processamento;
- prioridade por usuário ou reunião.

---

## Fase 4 — Chatbot contextual da reunião

### Objetivo

Permitir perguntas e respostas baseadas exclusivamente no conteúdo de uma
reunião analisada.

### Fluxo RAG sugerido

```text
pergunta do usuário
→ embedding da pergunta
→ busca dos chunks semelhantes no pgvector
→ montagem do contexto
→ chamada ao modelo
→ resposta com referências aos chunks
```

### API sugerida

```http
POST /analises/{analysis_id}/chat
```

Exemplo:

```json
{
  "question": "Quais decisões foram tomadas sobre a integração com o ERP?"
}
```

Resposta sugerida:

```json
{
  "answer": "Foi decidido marcar uma reunião técnica na sexta-feira.",
  "sources": [
    {
      "chunk_id": "uuid",
      "chunk_index": 1,
      "excerpt": "Foi decidido marcar uma reunião técnica sexta-feira.",
      "similarity": 0.91
    }
  ]
}
```

### Requisitos de precisão

- responder somente com base nos chunks recuperados;
- declarar quando não houver evidência suficiente;
- citar chunks e trechos usados;
- não misturar dados de reuniões diferentes;
- validar permissão do usuário para acessar a reunião;
- permitir configurar quantidade mínima e máxima de fontes;
- registrar modelo e chunks utilizados na resposta.

### Histórico de conversa

Estrutura futura sugerida:

```text
ai.chat_sessions
ai.chat_messages
ai.chat_message_sources
```

O histórico deve guardar pergunta, resposta, modelo, fontes, duração e consumo
de tokens.

### Critérios de aceite

- perguntas recuperam apenas chunks da análise selecionada;
- respostas apresentam fontes verificáveis;
- falta de contexto produz uma resposta explícita, sem invenção;
- usuário sem permissão não acessa a reunião;
- histórico pode ser retomado sem perder referências.

---

## Fase 5 — Métricas reais e observabilidade

### Objetivo

Medir custo computacional, desempenho e qualidade de cada etapa.

### Dados recomendados

- `prompt_eval_count`;
- `eval_count`;
- tempo de carregamento do modelo;
- tempo de avaliação do prompt;
- tempo de geração;
- tempo do embedding;
- modelo e versão;
- thinking utilizado;
- limite de saída;
- quantidade de retries;
- erro por etapa;
- tempo total real da análise.

### Observabilidade

- logs estruturados em JSON;
- `analysis_id` em todas as mensagens;
- métricas Prometheus;
- tracing entre backend Java, FastAPI, Ollama e Postgres;
- dashboard de latência por modelo;
- alerta para análises presas ou com taxa elevada de falhas.

---

## 11. Ordem recomendada de implementação

```text
1. Status por etapa e histórico de tentativas
2. Reprocessamento de partes ausentes
3. Processamento assíncrono
4. Registro de modelo e métricas reais
5. Seleção de modelo por usuário autorizado
6. Busca vetorial por reunião
7. Chatbot com fontes
8. Histórico de conversas e observabilidade avançada
```

A base para o chatbot depende de embeddings confiáveis, filtros corretos por
reunião e permissão de acesso. Por isso, reprocessamento, status detalhado e
auditoria devem ser implementados antes da experiência de chat.

---

## 12. Definição de sucesso

O roadmap estará completo quando:

- modelos puderem ser selecionados com segurança;
- toda análise registrar sua configuração de execução;
- falhas puderem ser retomadas somente a partir da etapa necessária;
- o processamento não depender de uma conexão HTTP longa;
- perguntas sobre uma reunião forem respondidas com fontes verificáveis;
- nenhuma resposta utilizar dados de outra reunião;
- métricas permitirem comparar precisão, latência e estabilidade por modelo.
