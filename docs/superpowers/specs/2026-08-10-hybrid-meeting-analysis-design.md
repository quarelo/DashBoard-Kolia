# Análise híbrida e controlada de transcrições

## Objetivo

Transformar uma transcrição textual diarizada em dados estruturados para os
dashboards do KOLIA, com baixo consumo de CPU e memória. A análise visual deve
ficar disponível antes da indexação semântica. Não há captura nem transcrição
de áudio neste fluxo.

O ambiente de referência é uma VPS com 2 vCPU, 8 GB de RAM e 100 GB NVMe. O
modelo de análise inicial é `qwen3:1.7b`, servido pelo Ollama.

## Restrições observadas

- O Ollama observado durante o teste carregou um runner com um único slot e
  contexto de 4.096 tokens.
- A inferência usa CPU e aproximadamente 1,9 GB de RAM no teste atual.
- Chamadas simultâneas não devem ser presumidas como paralelas: com um slot,
  elas são enfileiradas e podem aumentar latência e memória.
- A transcrição pode conter anonimizações como `[PESSOA]`, `[EMPRESA]` e
  `[LOCAL]`. A análise não pode inventar os valores omitidos.
- A transcrição não contém necessariamente duração, data, NPS ou papéis dos
  participantes.

## Arquitetura escolhida

O processamento será híbrido e terá duas fases independentes:

1. análise para dashboard;
2. geração posterior de embeddings para busca semântica e chat.

O fluxo será:

```text
transcrição pronta
→ sanitização e contagem de tokens
→ divisão em chunks
→ extração factual de cada chunk, com concorrência limitada
→ análise compacta dos fatos extraídos
→ consolidação determinística e, quando necessária, consolidação pelo modelo
→ persistência e liberação do dashboard
→ embeddings em segundo plano, um chunk por vez
→ liberação da busca semântica
```

O limite de geração concorrente será configurável. O padrão seguro para a VPS
de referência será `1`. O valor `2` só deve ser usado quando o Ollama estiver
configurado com capacidade real para dois runners/slots e o benchmark mostrar
ganho. A expressão "controlado" significa que o serviço aplica esse limite e
não cria uma tarefa irrestrita por chunk.

## Unidades do sistema

### Preparação da transcrição

Responsável por normalizar o texto, preservar as marcações de locutor, contar
tokens e criar chunks com sobreposição suficiente para não perder contexto na
fronteira. Não interpreta conteúdo.

### Extrator factual

Recebe um chunk e retorna apenas fatos sustentados pelo texto:

- resumo do trecho;
- locutores e participantes identificáveis;
- cliente e segmento, quando explícitos;
- temas;
- problemas;
- decisões;
- dúvidas em aberto;
- próximos passos com responsável e prazo, quando explícitos;
- produtos e concorrentes mencionados;
- valores, quantidades e outras métricas;
- evidências textuais curtas;
- palavras-chave e tags candidatas.

Campos ausentes usam `null` ou lista vazia. Marcadores anonimizados são
preservados como marcadores, nunca completados por inferência.

### Analisador comercial

Recebe fatos já extraídos, não a transcrição completa, para reduzir tokens.
Produz:

- sentimento: positivo, neutro ou negativo;
- satisfação estimada pela IA, de 0 a 100;
- justificativa e confiança da satisfação estimada;
- score de risco, de 0 a 100;
- score de oportunidade, de 0 a 100;
- insights comerciais classificados;
- prioridade de cada insight;
- recomendações fundamentadas nos fatos.

O campo de satisfação deve ser apresentado como inferência e nunca como NPS.
A escala mede sinais conversacionais, não a resposta a uma pesquisa formal.

### Consolidador

Remove duplicações decorrentes da sobreposição entre chunks e combina os
resultados. Contagens, médias, prioridades e distribuições são calculadas em
Python. Uma chamada de consolidação ao modelo será usada apenas quando fatos de
chunks diferentes precisarem de síntese textual; reuniões de um único chunk
não serão reinterpretadas.

### Indexador semântico

Gera e persiste embeddings depois de o dashboard ficar pronto. Opera de forma
sequencial por padrão. Uma falha nesta fase não invalida a análise já entregue.

## Contrato de saída

A resposta detalhada da reunião deverá conter:

- metadados: identificadores, título, cliente, segmento e data recebida;
- processamento: estado, tokens, chunks e tempos por etapa;
- participantes: identificador do locutor, nome, papel e organização quando
  identificáveis;
- análise: resumo, temas, decisões, problemas, dúvidas, ações e evidências;
- comercial: produtos, concorrentes, métricas, riscos e oportunidades;
- avaliação: sentimento, satisfação estimada, confiança e justificativa;
- insights: tipo, score, prioridade, resumo, evidência, produtos relacionados e
  recomendação;
- indexação: estado e eventual mensagem de erro.

Os tipos de insight inicialmente suportados serão os já esperados pelo
frontend: `churn_risk`, `upsell_opportunity`, `product_feedback`,
`sentiment_alert` e `competitive_mention`.

## Mapeamento para o frontend

Os dados simulados de reuniões e insights serão substituídos por consultas à
API. As agregações do dashboard serão derivadas dos registros persistidos:

- reuniões analisadas: quantidade em estado visualmente disponível;
- clientes em risco: insights de churn acima do limiar configurado;
- oportunidades: insights de upsell;
- satisfação média: média da satisfação estimada, identificada como IA;
- distribuição de riscos: prioridade dos insights;
- oportunidades por categoria: tipo e score dos insights;
- evolução do sentimento: agrupamento mensal;
- produtos mencionados: ocorrências e polaridade associada;
- reuniões e insights recentes: data de criação ou data informada.

Na página da reunião, duração permanecerá ausente quando não vier nos metadados.
O sistema não tentará derivar duração de uma transcrição sem timestamps.

## Estados e disponibilidade

Estados principais:

```text
PROCESSING
ANALYZING
DASHBOARD_READY
EMBEDDING
DONE
FAILED_ANALYSIS
DASHBOARD_READY_WITH_EMBEDDING_ERROR
```

`DASHBOARD_READY` é a fronteira de latência percebida pelo usuário. A API deve
permitir consultar o resultado nesse estado. `DONE` indica que os embeddings
também estão disponíveis.

## Medição de desempenho

Serão persistidos, em milissegundos:

- preparação;
- extração factual total e por chunk;
- análise comercial;
- consolidação;
- tempo até `DASHBOARD_READY`;
- embeddings total e por chunk;
- tempo total até `DONE`.

O benchmark utilizará a transcrição fornecida pelo usuário. O resultado será
reportado junto com modelo, tokens, chunks, limite de concorrência e recursos
observados. Não haverá estimativa fixa antes da execução real.

## Tratamento de falhas

- Resposta inválida do modelo falha apenas a etapa correspondente e registra
  uma mensagem útil.
- A análise poderá repetir uma chamada inválida uma vez, sem paralelizar a
  repetição.
- Falha definitiva na análise resulta em `FAILED_ANALYSIS`.
- Falha de embedding preserva o dashboard e resulta em
  `DASHBOARD_READY_WITH_EMBEDDING_ERROR`.
- Reprocessar embeddings não repete a análise.
- Resultados parciais não serão silenciosamente substituídos por mocks.

## Estratégia de testes

O desenvolvimento seguirá testes antes do código de produção. A cobertura
incluirá:

- schemas e instruções anti-alucinação dos prompts;
- campos ausentes e anonimizações;
- um e vários chunks;
- deduplicação da sobreposição;
- limite configurável de concorrência;
- dashboard disponível antes dos embeddings;
- falha e nova tentativa de geração;
- falha isolada e reprocessamento de embeddings;
- tempos persistidos e transições de estado;
- agregações consumidas pelo frontend;
- integração das páginas com a API;
- benchmark integral da transcrição de referência.

## Fora do escopo

- transcrição de áudio ou vídeo;
- identificação biométrica dos locutores;
- descoberta dos valores substituídos por marcadores de anonimização;
- NPS formal;
- paralelismo irrestrito;
- mudança do modelo sem benchmark comparativo.
