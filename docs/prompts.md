# Inventário de prompts

Todo texto que o projeto manda para um modelo, onde ele vive e sob quais
parâmetros roda. Levantado em 2026-09-09.

Oito prompts de geração, em dois arquivos, mais as consultas de embedding do
`rag_service`. Não existe prompt em `backend/` nem em `frontend/`: os dois só
repassam.

---

## Mapa rápido

| # | Prompt | Arquivo | Modelo | Quando roda |
|---|---|---|---|---|
| 1 | Chat, primeira tentativa | `chat_service._build_prompt` | `MODEL` | uma vez por pergunta |
| 2 | Chat, releitura | `chat_service._build_reread_prompt` | `MODEL` | só quando a 1ª recusa, copia a pergunta ou responde em <4 palavras |
| 3 | Catálogo de motivos | `llm_service.MOTIVE_CATALOGUE` | — | fragmento injetado no #4 |
| 4 | Resumo por chunk | `llm_service.generate_chunk_summary` | `CHUNK_MODEL` | uma vez por chunk (até `MAX_LLM_CHUNKS=15`) |
| 5 | Consolidação | `llm_service.consolidate_summaries` | `CONSOLIDATION_MODEL` | uma vez por análise |
| 6 | Completar campos ausentes | `llm_service.complete_missing_fields` | `CONSOLIDATION_MODEL` | só quando a consolidação deixou campo vazio |
| 7 | Classificação de produtos | `llm_service.classify_products` | `CONSOLIDATION_MODEL` | uma vez por análise, se `product_grounding_enabled` |
| 8 | Reparo de JSON | inline em `llm_service._generate_json` | o mesmo da chamada que falhou | só quando o JSON volta inválido e `OLLAMA_JSON_REPAIR_ENABLED` |

Hoje `MODEL`, `CHUNK_MODEL` e `CONSOLIDATION_MODEL` apontam todos para
`qwen2.5:3b`.

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
Fragmento, não prompt completo. Injetado no #4 quando
`chunk_motive_classification=True` (o padrão).

Lista os cinco códigos de churn e os cinco de oportunidade, cada um com uma
linha de definição, e instrui que **lista vazia é a resposta correta** quando
não houver sinal.

**Duas coisas contraintuitivas registradas no código:**

- Manter o catálogo no prompt foi medido **2,3x mais rápido** (132s contra 301s,
  0 truncamentos contra 8). Sem ele o modelo divaga em `pontos_chave` e estoura o
  orçamento de tokens, e cada estouro custa um retry inteiro.
- Os códigos que o modelo declara **não são usados**: `trust_declared_motives`
  está `False`, e o score de churn sai das regras regex de `motive_rules.py`.
  O catálogo fica porque ancora a saída, não porque alguém acredita nela.

---

## 4. Resumo por chunk

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

## 5. Consolidação

**`ia/src/app/services/llm_service.py::consolidate_summaries`**
Modelo `CONSOLIDATION_MODEL` · `temperature=0` · `num_predict=384` ·
`think=OLLAMA_CONSOLIDATION_THINK` (false) · `format=FINAL_SUMMARY_SCHEMA`

Recebe os resumos parciais e produz os 13 campos do `final_summary` — os mesmos
que o chat roteia hoje. Pede para **reconstruir a reunião, não contar rótulos**.

Regras que repetem as do #4 num nível acima, mais duas próprias:

- Produto e persona **não podem** voltar vazios havendo qualquer evidência
  explícita
- Em `evidencias`, associar cada insight ao trecho literal mais próximo
- **"Os resumos têm pontos prefixados por categoria, mas os rótulos podem estar
  errados: valide o sentido do texto antes de consolidar"** — o prompt não confia
  na saída do #4

---

## 6. Completar campos ausentes

**`ia/src/app/services/llm_service.py::complete_missing_fields`**
Modelo `CONSOLIDATION_MODEL` · `temperature=0` · `num_predict=max(384, 768)` ·
`think=false` · `format` = schema **só dos campos que faltam**

O prompt mais curto do projeto, quatro linhas: preencher somente os campos
ausentes, usar apenas os fatos dos resumos parciais, não alterar campos
existentes, não inventar. Recebe o JSON parcial e os resumos.

O schema restrito é o que impede o modelo de reescrever o que já estava certo.

---

## 7. Classificação de produtos

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

## 8. Reparo de JSON

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
CHAT_TEMPERATURE=0.4          apenas o chat; todo o resto roda em 0
CHAT_NUM_PREDICT=512          CHAT_CONTEXT_LENGTH=8192
OLLAMA_CHUNK_NUM_PREDICT=256  teto 512, calibrado para o gemma3:1b
OLLAMA_CONSOLIDATION_NUM_PREDICT=384
OLLAMA_THINK=True             mas os três caminhos JSON passam think=false
```

`OLLAMA_CHUNK_NUM_PREDICT` e `chunk_motive_classification` foram medidos contra
o `gemma3:1b`. O chat migrou para `qwen2.5:3b` e o pipeline também; nenhum dos
dois foi remedido no modelo novo.
