# Inventário de prompts

Todo texto que o projeto manda para um modelo, onde ele vive e sob quais
parâmetros roda. Levantado em 2026-09-09.

Nove prompts de geração, em dois arquivos, mais as consultas de embedding do
`rag_service`. Não existe prompt em `backend/` nem em `frontend/`: os dois só
repassam.

---

## Mapa rápido

| # | Prompt | Arquivo | Modelo | Quando roda |
|---|---|---|---|---|
| 1 | Chat, primeira tentativa | `chat_service._build_prompt` | `MODEL` | uma vez por pergunta |
| 2 | Chat, releitura | `chat_service._build_reread_prompt` | `MODEL` | só quando a 1ª recusa, copia a pergunta ou responde em <4 palavras |
| 3 | Catálogo de motivos | `llm_service.MOTIVE_CATALOGUE` | — | fragmento injetado no #5 |
| 4 | Catálogo de concorrentes | `llm_service.COMPETITOR_CATALOGUE` | — | fragmento injetado nos #5 e #6 |
| 5 | Resumo por chunk | `llm_service.generate_chunk_summary` | `CHUNK_MODEL` | uma vez por chunk (até `MAX_LLM_CHUNKS=15`) |
| 6 | Consolidação | `llm_service.consolidate_summaries` | `CONSOLIDATION_MODEL` | uma vez por análise |
| 7 | Completar campos ausentes | `llm_service.complete_missing_fields` | `CONSOLIDATION_MODEL` | só quando a consolidação deixou campo vazio |
| 8 | Classificação de produtos | `llm_service.classify_products` | `CONSOLIDATION_MODEL` | uma vez por análise, se `product_grounding_enabled` |
| 9 | Reparo de JSON | inline em `llm_service._generate_json` | o mesmo da chamada que falhou | só quando o JSON volta inválido e `OLLAMA_JSON_REPAIR_ENABLED` |

Hoje, no `.env` da raiz: `MODEL=qwen3.5:4b-q4_K_M`, `CHUNK_MODEL=qwen2.5:3b`,
`CONSOLIDATION_MODEL=qwen3.5:4b-q4_K_M` — trocado de `gemma3:1b` em
2026-09-10, junto com a GPU passando a ser usada pelo `ollama` (bloco `deploy`
em `docker-compose.yml`; sem ele o Ollama rodava só em CPU mesmo com a GPU
disponível na máquina). Ver "Onde ficam os parâmetros" no fim deste documento
para os números que sustentam a troca.

---

## 1. Chat — primeira tentativa

**`ia/src/app/services/chat_service.py::_build_prompt`**
Modelo `MODEL` · `temperature=CHAT_TEMPERATURE` (0.4) · `num_predict=512` ·
`num_ctx=8192` · `think=false` · timeout 120s · sem `format` (texto livre)

Recebe o histórico da conversa e as evidências recuperadas. Estrutura:

- Instrução de aterramento: usar **somente** as evidências, não supor, não
  completar lacunas
- Frase de escape exata para quando as evidências não responderem
- "A primeira evidência é a mais relevante" — a seleção ordena por score híbrido
- Exigência de **frase completa**, com exemplo do que não serve ("em vez de
  'Sim', escreva o que a reunião diz")
- Bloco de defesa contra injeção: as evidências são declaradas CONTEÚDO NÃO
  CONFIÁVEL e o modelo é instruído a não seguir ordens dentro delas
- Proibição de criar citações — o servidor as anexa

**Por que a exigência de frase completa existe:** com `temperature=0.0` e sem
ela, o modelo respondia "Sim.", "Preço.", "Estoque.".

---

## 2. Chat — releitura

**`ia/src/app/services/chat_service.py::_build_reread_prompt`**
Mesmos parâmetros do #1. Roda no máximo uma vez por pergunta.

Repete as regras de aterramento e injeção do #1 e muda só o que a primeira
tentativa errou:

- Diz que **uma primeira leitura não achou a resposta** e pede releitura,
  inclusive do que estiver dito de forma indireta
- Recebe 3 trechos em vez de 1 (`_REREAD_EVIDENCE_COUNT`)
- Pede o que os trechos dizem sobre o assunto quando não houver resposta exata
- **A frase de escape fica no fim**, não no topo — no #1 ela aparece antes de o
  modelo ver qualquer evidência

**Medido:** transformou 6 respostas em 7 sobre 8 perguntas. Um exemplo (one-shot)
neste prompt foi testado e **piorou** — 2 recusas em 5 perguntas.

---

## 3. Catálogo de motivos

**`ia/src/app/services/llm_service.py::MOTIVE_CATALOGUE`**
Fragmento, não prompt completo. Injetado no #5 quando
`chunk_motive_classification=True` (o padrão).

Lista os cinco códigos de churn e os cinco de oportunidade, cada um com uma
linha de definição, e instrui que **lista vazia é a resposta correta** quando
não houver sinal.

**Duas coisas contraintuitivas registradas no código:**

- Manter o catálogo no prompt foi medido **2,3x mais rápido** (132s contra 301s,
  0 truncamentos contra 8). Sem ele o modelo divaga em `pontos_chave` e estoura o
  orçamento de tokens, e cada estouro custa um retry inteiro.
- Até 2026-09-10 os códigos que o modelo declarava **não eram usados**
  (`trust_declared_motives=False`, porque o 1B enumerava o catálogo inteiro). Com
  o `qwen3.5:4b-q4_K_M` a flag está ligada e os códigos declarados pontuam; uma
  declaração que cobre os cinco códigos é tratada como enumeração e descartada, e
  aí `motive_rules.py` decide. Ver "Por que churn e oportunidade davam 0" e
  "Terceira rodada" no fim deste documento.

---

## 4. Catálogo de concorrentes

**`ia/src/app/services/llm_service.py::COMPETITOR_CATALOGUE`**
Fragmento, não prompt completo. Injetado nos #5 e #6.

Lista os seis concorrentes conhecidos da TOTVS (SAP, Oracle, Sankhya, Senior
Sistemas, Omie, Microsoft Dynamics 365), cada um com uma linha de descrição —
mesmo formato do catálogo de motivos (#3).

**Por que existe:** antes dele, o único sinal de concorrência era a palavra
genérica "concorrente" — tanto no prompt quanto no detector determinístico de
`motive_rules.py`. Um cliente dizendo "hoje usamos SAP" não acionava nem um nem
outro. O catálogo dá nomes ao modelo para narrar em `pontos_chave` e nos campos
de `final_summary`; a mudança que de fato move o score de churn foi estender os
gatilhos de `MENCAO_CONCORRENTE` em `motive_rules.py` com esses mesmos nomes —
na época a ressalva do #3 valia — o código declarado não pontuava, quem pontuava
era a regex. Desde a "Terceira rodada" o código declarado pontua, e a regex virou
o caminho de reserva.

Um cuidado registrado na regra: "Senior Sistemas" exige a frase completa,
porque "sênior" sozinho é também o adjetivo comum de cargo ("gerente sênior"),
e a normalização do texto (minúsculas, sem acento) colapsa os dois na mesma
grafia.

---

## 5. Resumo por chunk

**`ia/src/app/services/llm_service.py::generate_chunk_summary`**
Modelo `CHUNK_MODEL` · `temperature=0` · `num_predict` adaptativo
(`chunk_num_predict`: `max(256, min(tokens//4, 512))`) · `think=OLLAMA_CHUNK_THINK`
(false) · `format=CHUNK_SUMMARY_SCHEMA` (JSON obrigatório)

É o prompt mais denso do projeto, e o mais caro: roda uma vez por chunk. Pede no
máximo 6 pontos curtos, cada um prefixado por uma de doze categorias (PRODUTO,
PERSONA, SENTIMENTO, CHURN, OPORTUNIDADE, BUDGET, GAP, PROBLEMA, FEEDBACK,
DÚVIDA, AÇÃO, EVIDÊNCIA).

Quase todo o texto é **desambiguação de categoria**, e cada regra existe por um
erro observado:

- "Diferencie o que é demonstração hipotética do vendedor do que é necessidade
  real do cliente"
- BUDGET é só desta compra — "não classifique métricas de exemplo (clientes,
  pedidos, atividades, quilômetros) como budget"
- CHURN exige cancelamento ou insatisfação explícita — "não use a palavra
  'cancelado' de um pedido como churn"
- SENTIMENTO é a percepção geral, não o sentimento de um exemplo narrado
- OPORTUNIDADE é item já existente no portfólio; GAP é o que ele não atende
- "Nunca devolva apenas nomes de categorias"

---

## 6. Consolidação

**`ia/src/app/services/llm_service.py::consolidate_summaries`**
Modelo `CONSOLIDATION_MODEL` · `temperature=0` ·
`num_predict=OLLAMA_CONSOLIDATION_NUM_PREDICT` (1536) ·
`think=OLLAMA_CONSOLIDATION_THINK` (false) · `format=FINAL_SUMMARY_SCHEMA`

Recebe os resumos parciais e produz os 13 campos do `final_summary` — os mesmos
que o chat roteia hoje. Pede para **reconstruir a reunião, não contar rótulos**.

Regras que repetem as do #5 num nível acima, mais duas próprias:

- Produto e persona **não podem** voltar vazios havendo qualquer evidência
  explícita
- Em `evidencias`, associar cada insight ao trecho literal mais próximo
- **"Os resumos têm pontos prefixados por categoria, mas os rótulos podem estar
  errados: valide o sentido do texto antes de consolidar"** — o prompt não confia
  na saída do #5
- Em `duvidas_em_aberto`, de 1 a 3 perguntas escritas pelo modelo sobre o que
  ficou em aberto na reunião inteira, nunca fala copiada; ver "Dúvidas em aberto
  com fala crua da transcrição — 2026-09-12"

---

## 7. Completar campos ausentes

**`ia/src/app/services/llm_service.py::complete_missing_fields`**
Modelo `CONSOLIDATION_MODEL` · `temperature=0` · `num_predict=max(OLLAMA_CONSOLIDATION_NUM_PREDICT, 768)` ·
`think=false` · `format` = schema **só dos campos que faltam**

O prompt mais curto do projeto, quatro linhas: preencher somente os campos
ausentes, usar apenas os fatos dos resumos parciais, não alterar campos
existentes, não inventar. Recebe o JSON parcial e os resumos.

O schema restrito é o que impede o modelo de reescrever o que já estava certo.

---

## 8. Classificação de produtos

**`ia/src/app/services/llm_service.py::classify_products`**
Modelo `CONSOLIDATION_MODEL` · `temperature=0` · `num_predict=192` ·
`think=false` · `format` com **enum montado a partir dos candidatos**

Recebe no máximo 5 candidatos reais, já pré-selecionados por similaridade contra
`ai.products` (pgvector). Nunca vê o catálogo inteiro.

Duas travas, uma no prompt e outra no schema:

- Prompt: "Nunca escreva um nome fora da lista de candidatos. Devolva lista vazia
  se nenhum candidato se aplica de fato; não force uma escolha."
- Schema: o enum é construído dos próprios candidatos, então um nome fora do
  catálogo é **impossível** de retornar, não apenas desencorajado

---

## 9. Reparo de JSON

**`ia/src/app/services/llm_service.py::_generate_json`** (literal inline)
Mesmo modelo da chamada que falhou · `temperature=0` · `num_predict=min(n, 192)`
· `think=false` · mesmo `format`

Duas linhas: reparar o texto e devolver só um objeto JSON válido que respeite o
schema, **sem acrescentar fatos**. Recebe os primeiros 8000 caracteres da
resposta quebrada.

Só dispara quando o parse falha e `OLLAMA_JSON_REPAIR_ENABLED=true`. Antes dele
há um retry com o dobro do `num_predict`, porque a causa mais comum de JSON
inválido é truncamento, não erro de sintaxe.

---

## Consultas de embedding

Não são prompts de geração, mas são texto escrito à mão que vai para um modelo
(`nomic-embed-text`) e decide o que é recuperado.

**`rag_service._GROUP_QUERIES`** — seis frases, uma por grupo de categorias, usadas
por `search_analysis_categories`. Os 13 campos compartilham essas seis consultas
para não pagar treze chamadas de embedding quase idênticas.

**`rag_service._CATEGORY_QUERY_GROUPS`** — descrição por campo. Hoje serve só de
documentação: `_CATEGORY_QUERY_CACHE` mapeia cada campo para um dos seis grupos.

**Aviso registrado:** essas descrições foram tentadas como base para roteamento
semântico do chat e **falharam** — 2 de 8 campos corretos, porque são consultas
de recuperação de passagem, não definições de campo (`feedback_produto` diz
"feedback sobre produtos usados" e ganha de `produto` na palavra "produtos").
Reescrevê-las para rotear deu 4 de 8. O roteamento em produção é léxico,
`chat_service._SUMMARY_ROUTES`, com 18/18 medidos.

---

## Onde ficam os parâmetros

```
OLLAMA_MODEL / OLLAMA_CHUNK_MODEL / OLLAMA_CONSOLIDATION_MODEL = qwen3.5:4b-q4_K_M
OLLAMA_CONTEXT_LENGTH=32768   CHAT_CONTEXT_LENGTH=32768
CHAT_TEMPERATURE              0.4 no config.py, 0.0 no docker-compose.yml — em
                              container vale o do compose; todo o resto roda em 0
CHAT_NUM_PREDICT=512
OLLAMA_CHUNK_NUM_PREDICT=384  teto 512; 0 truncamentos em 256/384/512
OLLAMA_CONSOLIDATION_NUM_PREDICT=1536  768 truncava as dúvidas raciocinadas
OLLAMA_CONSOLIDATION_THINK=false       true devolveu resposta vazia com schema
FAST_DETERMINISTIC_CONSOLIDATION=false
TRUST_DECLARED_MOTIVES=true
OLLAMA_THINK=True             mas os três caminhos JSON passam think=false
```

`OLLAMA_CHUNK_NUM_PREDICT` e `chunk_motive_classification` foram medidos contra
o `gemma3:1b`, e ainda não foram remedidos contra o `qwen2.5:3b` que assumiu
`CHUNK_MODEL` em 2026-09-10.

## Troca de modelo — 2026-09-10

Motivação: `MODEL`/`CHUNK_MODEL`/`CONSOLIDATION_MODEL` estavam todos em
`gemma3:1b`, rodando só em CPU (o serviço `ollama` não tinha reserva de GPU no
`docker-compose.yml`, mesmo a máquina tendo uma GTX 1070 Ti de 8GB). Medido nos
dois perfis exigidos pelo `CLAUDE.md` — a reunião curta (~63 tokens, extraída
do CSV de reuniões) e a reunião longa de `ia/tests/test_analisar.py` (~40 mil
tokens, 3 chunks na amostra) — com GPU habilitada, mesmos parâmetros de geração
em todos os modelos (só o modelo variou), contra seis candidatos:
`gemma3:1b`, `qwen2.5:3b`, `qwen3:4b-instruct`, `qwen3.5:4b-q4_K_M`,
`qwen2.5:7b-instruct`, `qwen3.5:9b-q4_K_M`.

**Achado principal, na consolidação (uma chamada por análise):** o `gemma3:1b`
produzia JSON com conteúdo trocado de campo — `budget.valor` chegava como
fragmento cru (`".4 mil}, "`), e o texto de `sentimento.justificativa` era
colado, palavra por palavra, dentro de `gap_produto` e `recomendacao_acao`. O
`qwen2.5:3b` corrigia os campos centrais mas devolvia as listas opcionais
(`gap_produto`, `problemas_identificados`, `feedback_produto`, `evidencias`,
`recomendacao_acao`, `duvidas_em_aberto`) sempre vazias, e repetia a mesma
corrupção de `budget.valor` do `gemma3:1b`. O `qwen3.5:4b-q4_K_M` foi o único
sem corrupção, com `evidencias` citando trechos literais da transcrição e
todas as listas preenchidas com conteúdo específico da reunião — ao custo de
consolidação **8-10x mais lenta** (80-100s contra 8-18s dos outros dois).
`qwen2.5:7b-instruct` ficou no meio (~60-63s, sem corrupção, mas com texto mais
genérico e repetido entre campos). `qwen3:4b-instruct` **falhou** na reunião
longa — `OllamaResponseError`, JSON truncado mesmo após o retry com o dobro do
orçamento de tokens. `qwen3.5:9b-q4_K_M` foi o mais lento de todos (~105-115s)
sem mostrar ganho de qualidade sobre o `4b-q4_K_M` que justificasse o custo
extra nos 8GB de VRAM disponíveis.

**No chat** (síncrono, timeout de 120s): todos os quatro modelos plausíveis
responderam em 5,5-10,7s, longe do limite. Mas `gemma3:1b` e `qwen2.5:3b`
devolveram só a frase-fato ("R$ 3 milhões") em vez da frase completa que o
prompt pede — o que `_is_too_short` já pega e manda para uma releitura, um
custo silencioso que `qwen3.5:4b-q4_K_M` e `qwen2.5:7b-instruct` não pagam,
por responderem certo já na primeira tentativa.

**Achado colateral, sem relação com o modelo escolhido:** os `pontos_chave` de
chunk saíram **idênticos** entre os três modelos testados de perto, porque
`_extract_deterministic_chunk_points` (regex determinística) sozinha já enche
o teto de 12 pontos nessa transcrição, antes de qualquer ponto gerado pelo
modelo entrar na lista. Isso significa que esta rodada não conseguiu comparar
a qualidade do `CHUNK_MODEL` de verdade — só a velocidade.

**Decisão:** `MODEL` e `CONSOLIDATION_MODEL` foram para `qwen3.5:4b-q4_K_M` — a
única saída sem corrupção e com conteúdo de fato específico da reunião, e o
custo de consolidação é pago uma vez por análise, em background. `CHUNK_MODEL`
foi para `qwen2.5:3b` — mais barato, já testado antes no projeto, e sem
evidência (pelo achado colateral acima) de que o `qwen3.5:4b-q4_K_M` valha o
custo de rodar até 15x por reunião. `qwen3:4b-instruct` e `qwen3.5:9b-q4_K_M`
ficam descartados: o primeiro quebra em entrada real, o segundo não mostrou
ganho que justifique ser o mais lento de todos.

## Segunda rodada de medição — 2026-09-10

Fechando o que a primeira rodada deixou em aberto, agora com o pipeline real
(`prepare_analysis` + `process_analysis_summaries` + `process_analysis_embeddings`,
os mesmos três passos que o `analysis_worker` dispara) sobre a reunião de
`ia/tests/test_analisar.py`: 40.008 tokens, 21 chunks.

**Contexto em 32768 cabe com folga.** Pico de 4.000 MiB dos 8.192 de VRAM, com
~1.200 MiB já do Windows/WSL — sobram 4,2 GB. GPU em 100% de utilização durante
os resumos, ou seja sem offload para CPU. Pico de RSS do processo: 94 MB.

**O caminho determinístico é a raiz do "trecho no lugar da resposta".** Com
`FAST_DETERMINISTIC_CONSOLIDATION=true` o `final_summary` sai do
`build_compact_final_summary` e o `consolidate_summaries` (#6) nunca roda.
Comparado na mesma reunião:

| | determinístico | consolidação por LLM (768) |
|---|---|---|
| total | 96s | 239s |
| `budget.valor` | `"A [L67]: parte de serviço, a parte de mensalidade, se [L73]: são [L67]: licenças compartilhadas..."` | `"Não identificado explicitamente como valor total da negociação, mas mencionados valores operacionais (ex: R$ 84,00..., R$ 1.000,00 para adiantamento)."` |
| `evidencias[].trecho` | `"AMEACA_CANCELAMENTO"`, `"Positivo"` | citação literal da transcrição |
| `evidencias[].insight` | template fixo por categoria | insight específico da reunião |

Como o `chat_service._SUMMARY_ROUTES` roteia a pergunta direto para esses campos,
o bloco cru com tags de locutor chegava ao leitor como resposta. Por isso
`FAST_DETERMINISTIC_CONSOLIDATION=false`. Os 143s a mais são pagos uma vez por
análise, em background.

**`OLLAMA_CHUNK_NUM_PREDICT` não era o gargalo.** Varredura 256/384/512 no
`qwen2.5:3b`: **0 truncamentos nos três**, com o modelo gastando 110-133 tokens
por resumo. O teto herdado do `gemma3:1b` nunca estava cortando nada. Ficou em
384 apenas como margem para o modelo mais verboso que assumiu o chunk.

**A regex determinística sufoca o modelo no chunk — e é pior que ele.** Com
`_extract_deterministic_chunk_points` neutralizado, dá para ver o que cada
modelo produziria sozinho:

- *determinístico* (o que ocupa os 12 slots hoje): 6 entradas de PERSONA, várias
  cortadas no meio da frase (`"representante ali que atende uma região, uma
  área, e ele vai fa"`), e dois GAP que não são gap (`"Eu posso pedir para vocês
  se a gente pode deixar a reunião gravada"`). Cobre 3 das 12 categorias.
- *`qwen2.5:3b`* (6,7s/chunk): fraco — código vazando
  (`"OPORTUNIDADE: PEDIDO_EXPANSÃO"`), rótulo puro (`"SENTIMENTO: Positivo"`, que
  o prompt proíbe) e enchimento (`"GAP: Nenhuma necessidade específica
  mencionada"`).
- *`qwen3.5:4b-q4_K_M`* (15,2s/chunk): fatos concretos, e cobrindo categorias que
  a regex nunca alcança — `"EVIDÊNCIA: ticket médio R$ 84,00 com queda de 28%"`,
  `"DÚVIDA: viés gerencial dos dashboards"`.

Daí o `CHUNK_MODEL` ter ido para `qwen3.5:4b-q4_K_M` também.

**Em aberto, e agora com evidência para decidir:** o merge em
`generate_chunk_summary` põe os pontos determinísticos primeiro e corta em 12,
então numa transcrição densa o modelo é integralmente descartado. Isso foi
desenhado quando o modelo era um 1B em que não dava para confiar; a medição
acima mostra que a premissa virou. Mexer na ordem é mudança de código, não de
`.env`, e a regex também é a rede que garante que campo nenhum volte vazio —
então vale medir a troca, não presumir.

**Ressalva do ambiente de teste:** essas rodadas usaram um Postgres local com
`ai.products` vazio, então `produto: []` nelas é artefato do catálogo ausente
(o grounding zera contra catálogo vazio), não resultado de modelo.

---

## Por que churn e oportunidade davam 0 em toda reunião — 2026-09-10

Sintoma relatado: `risco_churn` e `score_oportunidade` saíam 0 independentemente
da reunião. São três falhas empilhadas, medidas em 4 chunks da reunião de teste:

| Onde o score é calculado | Categorias que chegam | Churn | Oportunidade |
|---|---|---|---|
| regras na transcrição crua | — | 100 | 55 |
| `pontos_chave` como produção monta | PRODUTO 8, PERSONA 10, GAP 30 | **0** | **0** |
| só o modelo, sem a regex | SENTIMENTO, OPORTUNIDADE 4, DÚVIDA, EVIDÊNCIA 6, AÇÃO… | 0 | 0 |
| códigos que o modelo declara | — | 0 | 60 |

1. O score sai de `grouped["CHURN"]`/`grouped["OPORTUNIDADE"]`, que são os
   `pontos_chave` filtrados por prefixo — e a extração determinística enche os
   12 slots com PRODUTO/PERSONA/GAP, então **nenhum ponto dessas duas categorias
   chega a existir**.
2. Mesmo quando chega, as regras de `motive_rules.py` não disparam: elas foram
   escritas para a literalidade da transcrição e o modelo entrega paráfrase. O
   comentário em `analysis_service.py` afirmava que "as regras leem o texto que o
   modelo citou, que é a redação da transcrição, e não a paráfrase dele" — isso
   não é verdade na prática, e é onde o zero nasce.
3. O modelo declarava códigos válidos sob o schema enum, e ninguém lia:
   `trust_declared_motives` estava `False`.

**Rodar as regras na transcrição crua foi descartado.** Dá churn 100, e as quatro
frases que disparam são todas falso positivo: `"cancelado dentro do [empresa]"`
(status de pedido numa demo — o blocker não pega porque "cancelado" vem antes de
"pedido"), `"não ter nenhum vínculo com outro fornecedor"` (elogio a fornecedor
único lido como menção a concorrente), `"colocar trava no momento da venda"`
("trava" como funcionalidade), e `"30 dias sem comprar"` (dado de exemplo na tela
do CRM, sobre os clientes *do prospect*).

**O que foi feito:** `TRUST_DECLARED_MOTIVES=true` — o `config.py` já dizia "Turn
on with a model that can classify", e o `qwen3.5:4b-q4_K_M` classifica. Mas
ligar a confiança sozinha reabre exatamente o risco que a flag protegia: um
modelo com espaço **enumera** o catálogo em vez de escolher. Então a proteção
mudou de lugar, para `_declared_unless_enumerated` em `analysis_service.py`: uma
declaração que cobre 4 ou mais dos 5 códigos é descartada e as regras decidem.
Quatro e não três, porque três pode ser leitura legítima — medido.

**Validação** (casos com resposta conhecida, um deles exercitando o catálogo de
concorrentes do #4):

| Caso | Esperado | Churn | Oportunidade |
|---|---|---|---|
| demo com prospect interessado | churn 0 | **0** | 60 (`INTERESSE_NOVO_MODULO`, `PEDIDO_EXPANSAO`) |
| ameaça explícita de cancelamento | churn alto | **80** (`AMEACA_CANCELAMENTO`, `INSATISFACAO_EXPLICITA`) | 0 |
| cita SAP e Sankhya pelo nome | pegar sem a palavra "concorrente" | **100** (inclui `MENCAO_CONCORRENTE`) | 50 |
| pedido de expansão com verba e prazo | oportunidade alta | 0 | **90** (`PEDIDO_EXPANSAO`, `MENCAO_BUDGET`, `INTERESSE_NOVO_MODULO`) |

**Ressalva honesta:** no caso do concorrente o modelo declarou também
`AMEACA_CANCELAMENTO` e `INSATISFACAO_EXPLICITA`, e nenhum dos dois está no
texto — ninguém ameaçou cancelar nem reclamou, só disseram que o preço do outro
ficou abaixo. O score deixou de estar preso em zero e acerta a direção, mas
**super-declara no lado negativo**. A falha histórica grave (transformar uma demo
em churn 100) não se repetiu — a demo continua 0. Vale calibrar com reuniões
reais rotuladas antes de tratar o número como confiável para decisão comercial.

---

## Terceira rodada — 2026-09-10

**O score das reuniões longas não passava pela tabela.** A confiança nos códigos
declarados e a guarda de enumeração vivem em `build_compact_final_summary`. Com
`FAST_DETERMINISTIC_CONSOLIDATION=false`, reunião de um chunk continuava pontuando
pela tabela de motivos, mas reunião de vários chunks ficava com o 0-100 livre que o
`consolidate_summaries` escreve — duas escalas no mesmo dashboard, e a guarda
contornada justamente nas reuniões maiores. Agora, depois da consolidação por LLM,
`risco_churn` e `score_oportunidade` são recalculados pela tabela; o resto do resumo
continua sendo do LLM.

**Definições de churn apertadas no catálogo de motivos (#3).**
`AMEACA_CANCELAMENTO` passou de "fala em cancelar" para "diz que vai cancelar,
encerrar, rescindir ou não renovar"; `INSATISFACAO_EXPLICITA` passou de "demonstra
insatisfação" para "diz, com as próprias palavras, que está insatisfeito"; e o
catálogo agora avisa que avaliar concorrente ou achar o preço dele menor é só
`MENCAO_CONCORRENTE`. Validação em 7 casos de resposta conhecida, antes → depois:

| Caso | Churn | Oportunidade |
|---|---|---|
| demo com prospect interessado | 0 → 0 | 60 → 60 |
| ameaça explícita de cancelamento | 80 → 80 | 0 → 0 |
| avaliando SAP e Sankhya antes de renovar | **100 → 75** | 50 → 30 |
| pedido de expansão com verba e prazo | 0 → 0 | 90 → 100 |
| controle: usou Omie no passado, satisfeito hoje | 0 → 0 | 35 → 15 |
| controle: reclamação leve de cliente satisfeito | 0 → 0 | 0 → 0 |
| controle: dado de inatividade na tela da demo | 0 → 0 | 60 → 60 |

A `INSATISFACAO_EXPLICITA` inventada no caso do concorrente sumiu; a
`AMEACA_CANCELAMENTO` ficou, e "avaliando as duas opções antes de renovar" é
ambíguo o bastante para não forçar mais o prompt. O controle do dado de demo não
justificou regra nenhuma: o modelo já não marcava inatividade com o prompt antigo,
então nada foi acrescentado para ele — prompt maior aqui já custou truncamento antes.

**Guarda de enumeração: piso de 4 para 5.** No caso da expansão, o prompt novo fez
o modelo declarar quatro códigos (`PEDIDO_EXPANSAO`, `MENCAO_BUDGET`,
`PRAZO_DEFINIDO`, `INTERESSE_NOVO_MODULO`), e os quatro estão no texto. Com o piso em
4, essa leitura correta seria descartada. A falha histórica era declarar os cinco.

**Recusas vazando como resposta do chat.** A calibração do detector de cópia (12
perguntas de recuperação, 13 gerações do `qwen3.5:4b-q4_K_M` sobre a reunião de 40
mil tokens) não encontrou cópia nenhuma: o maior trecho literal numa resposta teve
47 caracteres, no máximo 23% dela, e nenhuma resposta estava inteira dentro de um
trecho. Os limiares de 300 caracteres e 50% ficam longe do comportamento legítimo e
foram mantidos. A mesma rodada achou outro vazamento: *"Nenhuma evidência na
transcrição menciona a opinião do cliente..."* e *"Nenhum dos trechos trata sobre a
situação em que o vendedor está sem conexão..."* foram servidas como resposta
fundamentada, com citação embaixo, porque `_is_unknown_answer` só reconhecia "não
encontrei" e "não há informação". Agora recusa que começa negando e fala dos trechos
ou das evidências também cai no fallback.

As duas eram, além disso, **recusas falsas** — a transcrição fala de fornecedor
único e de trabalhar sem conexão. Isso é problema de recuperação ou de leitura, não
de detecção, e continua em aberto.

**Código morto removido.** `infer_churn_motives` e `infer_opportunity_motives`, em
`scoring_service.py`, não eram chamadas pela produção — só pelos próprios 15 testes.
A inferência por texto que vale é a de `motive_rules.py`.

**Ordem do merge no chunk.** `generate_chunk_summary` passou a pôr os pontos do
modelo primeiro; a regex determinística completa o que sobra, sinais comerciais na
frente e no máximo dois pontos por categoria. Mistura de categorias em
`pontos_chave` nos 4 primeiros chunks da reunião longa:

| Merge | Categorias | Score pela regex de reserva |
|---|---|---|
| regex primeiro (prompt antigo) | PRODUTO 8, PERSONA 10, GAP 30 — 3 categorias | churn 0 · oport. 0 |
| modelo primeiro, sem limite | DÚVIDA 24, EVIDÊNCIA 6, OPORTUNIDADE 5, BUDGET 4, SENTIMENTO 3 e mais 5 | churn 0 · oport. 40 |
| modelo primeiro, até 2 por categoria (atual) | DÚVIDA 11, GAP 8, PRODUTO 7, EVIDÊNCIA 6, OPORTUNIDADE 5, BUDGET 4 e mais 4 | churn 0 · oport. 40 |

O limite existe porque a regex de DÚVIDA trata toda frase com "?" como dúvida:
sem ele, a enxurrada de GAP só virou uma enxurrada de DÚVIDA. O corte interno de 12
dentro de `_extract_deterministic_chunk_points` também saiu, porque cortava na
ordem PRODUTO → PERSONA → GAP antes que a prioridade pudesse agir; o teto de 12
continua valendo, aplicado no merge.

**Rodada final ponta a ponta.** Pipeline real, com tudo acima em vigor:
`qwen3.5:4b-q4_K_M` nos três papéis, contexto 32768, consolidação por LLM (768
tokens), `TRUST_DECLARED_MOTIVES=true`, chunk com 384 tokens e até 15 chunks pelo
LLM. Reunião de 40.008 tokens, 21 chunks:

| Métrica | Valor |
|---|---|
| status | DONE |
| tempo total | 289,8s (preparo 0,4 · resumos e consolidação 278,2 · embeddings 11,1) |
| pico de VRAM | 5.640 MiB de 8.192 |
| pico de RSS do processo | 93 MB |
| `risco_churn` | 0 — "Nenhum sinal explícito identificado." |
| `score_oportunidade` | 90 — interesse em produto ainda não usado; pedido de ampliar escopo; orçamento citado |

Na mesma reunião: 96s com consolidação determinística, 239s com consolidação por
LLM e chunk no `qwen2.5:3b`, 290s agora com o `qwen3.5:4b-q4_K_M` também no chunk.
O pico de VRAM subiu de 4.000 para 5.640 MiB com o modelo maior no chunk, ainda com
~2,5 GB de folga.

**Em aberto — outra enxurrada, anterior a estas mudanças.** Nos 21 chunks da
rodada final, `pontos_chave` somou AÇÃO 151, EVIDÊNCIA 136 e PROBLEMA 130. Isso não
vem do merge acima: `merge_deterministic_evidence`, em `analysis_service.py`,
acrescenta sem limite os pontos de `build_deterministic_chunk_summary` a cada resumo
de chunk, e os 6 chunks que ficam fora do limite de 15 recebem só esses pontos.
Tudo isso entra no prompt da consolidação. Não foi medido se piora o resultado —
só que existe e que infla a entrada da consolidação.

---

## Quarta rodada — 2026-09-10

**A busca textual ignorava toda palavra acentuada.** `_lexical_query` tirava o
acento dos termos da pergunta antes do `to_tsquery`, mas o `search_vector` é
`to_tsvector('portuguese', content)`, sem `unaccent`. Na reunião longa, `conexao`
casou 0 de 123 passagens e `conexão` casou 2; `orcamento` casou 0 e `orçamento`,
33. Um termo que casa zero passagens era descartado como não discriminante, então
preço, orçamento, integração e conexão nunca entraram na busca textual. Agora o
termo vai com o acento da pergunta (`_query_terms`); a contagem e o casamento em
memória continuam sem acento.

**Trecho achado só pela busca textual era descartado sem ser lido.**
`_passage_search` só tem similaridade para acerto vetorial: o que só a busca
textual achou chegava com `similarity 0.0`, e o limiar de 0,55 descartava. O chat
agora leva como segunda opinião o acerto textual de termo mais raro
(`lexical_weight`). "O que o cliente acha de ter um fornecedor único?", recusada
com o chunk 1 achado e jogado fora, passou a responder com evidência [6, 1]:
*"O cliente considera a tendência de ter um único fornecedor como positiva, pois
isso permite que tudo fique integrado e concentrado em uma única solução."*

Os acertos textuais também passaram a ser ordenados pela raridade dos termos em
vez de `ts_rank`, que conta repetição. Isso é raciocínio, não medição isolada: a
pergunta sobre ficar "sem conexão" foi recuperada pela correção do acento, não
pela ordenação.

**Outra formulação de recusa.** *"Os trechos não mencionam a opinião do cliente
sobre ter um único fornecedor..."* também saía como resposta fundamentada, com
citação; entrou em `_EVIDENCE_REFUSAL`.

**Catálogo carregado e grounding funcionando.** `python -m scraper.main` carregou
302 produtos, sem falha, no banco local. A rodada ponta a ponta passou a devolver
`produto: ["TOTVS Distribuição e Varejo - Linha Winthor", "TOTVS Backoffice -
Linha Datasul"]`, antes `[]` por catálogo vazio. Não foi verificado se os dois
estão certos para essa reunião; a linha Datasul é a mesma que
`test_chat_service.py` usa como produto dela.

**Casos de resposta conhecida para o score.** `ia/scripts/evaluate_motives.py`
roda os 7 casos da terceira rodada e confere, por caso, os códigos que têm de
aparecer e os que não podem: 7 de 7. Não é verdade de campo — transcrições e
códigos esperados foram escritos à mão; a calibração de verdade precisa de
reuniões rotuladas pelo time comercial.

**Configuração e ambiente.**

- Os padrões de `config.py`, `docker-compose.yml` e `.env.example` agora batem
  com o que foi medido. Antes, quem subisse sem este `.env` pegava `gemma3:1b`,
  contexto 8192 e consolidação determinística.
- A reserva de GPU saiu do `docker-compose.yml` para o `docker-compose.gpu.yml`,
  ativado por `COMPOSE_FILE` no `.env`: no arquivo principal ela fazia o
  `docker compose up` falhar em máquina sem runtime NVIDIA. `docker compose config`
  mostra um dispositivo NVIDIA com o override e nenhum sem ele.
- 169 arquivos estavam "modificados" só por `\r` no fim da linha, e o shebang
  `#!/bin/sh\r` fazia os três testes de `test_install_model.py` falharem com
  `FileNotFoundError`. Um `.gitattributes` com `eol=lf` fixa o LF; os três passam.
- `test_summary_worker_honours_max_llm_chunks` chamava o Ollama de verdade: passava
  no compose, onde o container resolve o host `ollama`, e falhava na CI. Agora
  prende a consolidação determinística, que é o que o teste pressupunha. A suíte
  passa rodando das duas formas.

**A "enxurrada" da regex é o que a consolidação cita — o limite foi revertido.**
Na terceira rodada, `merge_deterministic_evidence` ganhou um limite de dois pontos
por categoria, porque somava AÇÃO 151, EVIDÊNCIA 136 e PROBLEMA 130 nos 21
chunks. A rodada ponta a ponta seguinte manteve só 1 evidência e voltou a errar o
budget. A/B com os mesmos pontos do modelo, mudando só o limite:

| | com limite | sem limite |
|---|---|---|
| `pontos_chave` | 368 | 571 |
| entrada da consolidação | 54.265 caracteres | 77.293 |
| evidências literais / geradas | 1 / 4 | 4 / 5 |
| `budget.valor` | "R$ 84,00" (preço de item) | "não identificado", com os preços citados no contexto |

As frases determinísticas são texto literal da transcrição, e a consolidação só
lê resumos: sem elas, o modelo passa a "citar" o que ele mesmo escreveu. O limite
saiu. O custo é ~42% a mais de entrada na consolidação, sem diferença de tempo
total medida (287s com limite, 290s sem). O filtro de evidências
(`_quoted_evidence`) ficou: com a entrada completa, ele descarta só a paráfrase
("O cliente elogia a capacidade da ferramenta..."), e a cobertura medida é
tudo-ou-nada — 0,0 ou 1,0 —, então o corte em metade não decide nenhum caso.

**Rodada ponta a ponta final.** Com tudo em vigor — enxurrada sem limite,
evidências verificadas, catálogo carregado e busca com acento —, na reunião de
40.008 tokens e 21 chunks:

| Métrica | Valor |
|---|---|
| status | DONE |
| tempo total | 302,5s (resumos e consolidação 288,7 · embeddings 13,5) |
| pico de VRAM | 5.838 de 8.192 MiB |
| pico de RSS do processo | 89 MB |
| `risco_churn` / `score_oportunidade` | 0 / 90 |
| `produto` | TOTVS Distribuição e Varejo - Linha Winthor; TOTVS Backoffice - Linha Datasul |
| `budget` | "não identificado" — R$ 84,00, R$ 11,63 e R$ 8,00 lidos como descontos e preços de itens |
| evidências | 4, todas citação literal da transcrição |

No chat, as 12 perguntas de recuperação sobre a mesma reunião foram todas
respondidas. Antes da busca com acento e da segunda opinião por termo raro, duas
delas eram recusas falsas, e uma dessas saía como resposta fundamentada.

**A segunda opinião olha qualquer similaridade.** A primeira versão só considerava
acertos textuais abaixo do limiar. Na pergunta sobre ficar "sem conexão", os
chunks 10 (similarity 0,704) e 1 (0,657) têm a palavra, mas perdiam o ranking para
o chunk 18, que não tem; a segunda opinião levava então o 17, que também não tem,
e a resposta saía certa sem nenhuma citação que a sustentasse. Agora ela considera
todo acerto textual de um chunk ainda não selecionado e fica com o de termo mais
raro: evidência [18, 10], com o 10 contendo "conexão" e "sincroniz". Suítes com
282 testes passando nas duas formas.

Custo observado, não isolado: com uma passagem a mais na evidência, "Como o
vendedor faz o input de itens hoje?" passou de *"precisa digitar manualmente os
itens"* para *"pode importar listas de itens via CSV"*. A transcrição sustenta a
primeira: o cliente pergunta como deixar de digitar o orçamento, e o CSV é recurso
mostrado na demo. É a confusão entre demonstração e realidade do cliente que o
prompt de chunk (#5) já tenta evitar, agora no chat. São 12 perguntas sem rótulo,
então fica registrado como risco, não como taxa.

---

## Dúvidas em aberto com fala crua da transcrição — 2026-09-12

No banco em uso, 4 de 10 análises mostravam no card itens como *"[L5]: Fala seu
[PESSOA], tudo bem?"* e *"DÚVIDA: [L13]: Você falou do migrar de ambiente do local
para nuvens, isso?"*: um cumprimento e uma confirmação, com a tag de locutor e o
rótulo interno do chunk. Vinha de três caminhos com a mesma origem:

| Análise | Chunks | Caminho |
|---|---|---|
| 5c1f17d2 | 5 | consolidação por LLM copiou os pontos de DÚVIDA como estavam |
| 1127528d | 1 | atalho de chunk único, determinístico |
| f7bb7324, 1eb71f25 | 21 | consolidação determinística anterior à troca de 2026-09-10 |

A origem comum era a regex de DÚVIDA em `_extract_deterministic_chunk_points`, que
transformava toda frase terminada em "?" num ponto `DÚVIDA:`, cumprimentos
incluídos. Na reunião longa a consolidação sintetizava; na de 5 chunks, copiava.

**Corrigido em três camadas.** `clean_open_questions` tira tag de locutor e rótulo
de categoria e descarta cumprimento, pergunta de confirmação ("né?", "isso?") e
item com menos de duas palavras reais — duas porque "Qual é o prazo?" tem
exatamente duas; marcador de anonimização como `[LOCAL]` não conta como palavra.
Ele filtra a regex na origem, as dúvidas do caminho determinístico,
e o resultado de `complete_missing_fields`, por onde todo caminho passa no fim do
pipeline e também o botão de recompletar. Os prompts de consolidação (#6) e de
recompletar (#7) ganharam a regra de escrever com as próprias palavras, nunca
copiando fala, tag ou rótulo.

**Dúvidas raciocinadas, e a reunião de 1 chunk também passa pelo LLM.** Filtrar a
fala crua não bastava: o pedido era um ponto em aberto pensado, como *"A equipe do
cliente estará disponível para o levantamento ou será necessário enviar o checklist
por escrito?"*, com mais tempo aceito em troca. A regra do #6 passou a pedir de 1 a
3 perguntas sobre a reunião inteira: o que foi prometido e não confirmado, o que o
cliente não sabe ou não decidiu, o que depende de alguém ausente, o que ficou sem
prazo ou responsável. O atalho de chunk único saiu, porque sem consolidação as
dúvidas de uma reunião curta eram só as frases com "?" que a regex pegava.

Medido só a consolidação, com os mesmos resumos de chunk em cada perfil:

| Perfil | `think=false`, 768 | `think=true`, 2048 | `think=false`, 1536 |
|---|---|---|---|
| curta (1 chunk) | 28,5s | vazia após 368 tokens | 19,8s |
| 5 chunks (5c1f17d2) | 77,9s, truncou e repetiu (1355 tokens) | vazia após 972 tokens | 49,7s, 1279 tokens |
| longa (21 chunks) | 109,2s, truncou e repetiu (1256 tokens) | vazia após 1232 tokens | 76,3s, 1116 tokens |

- **`think` fica desligado.** Com o schema JSON, o modelo gastou o orçamento
  pensando e devolveu 0 caracteres nos três perfis.
- **`OLLAMA_CONSOLIDATION_NUM_PREDICT` subiu de 768 para 1536.** A resposta com as
  dúvidas pensadas passa de 768 tokens: truncava e pagava uma segunda chamada. Com
  1536, nenhuma truncou, e o tempo caiu 28s e 33s nos perfis longos.
- A terceira coluna rodou com uma linha a mais no prompt, proibindo perguntar por
  dado anonimizado. Ela não mudou a reunião curta, que ainda devolveu *"Quem é o
  [LOCAL]?"*, e saiu. Quem cobre esse caso é o filtro.

Dúvidas obtidas na terceira coluna:
- 5 chunks: *"O cliente confirmou que a migração para o ambiente Prime pode ser
  executada no próximo fim de semana?"*, *"Qual é a data exata até onde o cliente
  está disposto a adiar a migração devido às pendências com fornecedores
  externos?"* e *"O cliente autorizou formalmente a alteração do contrato atual
  para incluir as licenças Progress adicionais necessárias?"*
- longa: *"Como será o desenvolvimento conjunto das customizações solicitadas?"* e
  *"Qual a viabilidade técnica de integrar a leitura de arquivos via IA para
  montagem de pedidos?"*
- curta: nenhuma depois do filtro. O trecho é o vendedor narrando uma demonstração,
  sem nada em aberto, e a lista vazia não é recompletada no pipeline.

**Análises já gravadas não mudam.** O backend lê `ai.meeting_analyses.final_summary`
direto, então o card de uma análise antiga só melhora se ela for reprocessada ou se
o campo for regravado.

**A suíte da `main` estava vermelha.** Depois do merge do PR #11, 8 testes de
`test_analysis_service.py` falhavam no próprio commit `13a3265`: o serviço passou a
chamar `generate_chunk_summary` e `consolidate_summaries` com `metadata_context=`,
e os mocks aceitavam só o texto. Os mocks agora aceitam os argumentos novos; 287
testes passam no compose e do jeito que a CI roda.

### Os outros campos de texto do card — reunião 1263093 do CSV

Rodada no banco em uso, em 4 chunks e 157s. O raciocínio da IA ficou como está, por
decisão do time; só o que era defeito de código mudou.

- **Fala crua durante o processamento.** Enquanto a análise rodava, Problemas
  Identificados mostrava *"[L19]: assim, é inviável hoje o pessoal do fiscal dando
  [L66]: manutenção..."*. `clean_card_items` tira tag de locutor e rótulo de
  categoria de oportunidade, gap, problemas, feedback e ações, no resumo preliminar,
  no parcial e no final. Diferente das dúvidas, não descarta item curto.
- **Item cortado.** *"... Lentidão no retorno do time de produto (48h"* tinha
  exatamente 180 caracteres, o `maxLength` do `FINAL_LIST_SCHEMA`: a gramática
  parou a string no meio. Um item com exatamente esse tamanho e sem pontuação final
  volta até a última frase completa. Item determinístico mais longo não é cortado,
  porque o critério é o tamanho exato do schema.
- **Vírgula no fim.** O modelo escreveu *"(48h úteis).,"* e *"regras),"*; o
  separador final sai.

**Evidências vazias ficaram como estão.** A consolidação devolveu 5 evidências, e
o `trecho` de todas era a frase do resumo do chunk (*"Cliente expressa intenção de
rescindir contrato..."*), não da transcrição, então `_quoted_evidence` descartou as
5. Trocar cada uma pela frase da transcrição mais parecida não se sustentou na
calibração: as frases certas ficaram entre 0,12 e 0,28 de palavras em comum, e
evidências da reunião longa, que não têm nada a ver com esta, chegaram a 0,30.
Nenhum limiar separa as duas, e "48 horas úteis" casou com a frase errada. A causa
é a consolidação ver só os resumos.
