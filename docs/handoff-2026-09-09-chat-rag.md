# Handoff — chat RAG: por que não respondia e o que mudou

Branch `fix/rag-chatbot-response`. Tudo commitado, incluindo a migração `0007`.
267 testes passando (`ia`), TypeScript do frontend limpo, cinco serviços no ar.

O relato de entrada foi: *"o RAG não me responde, independente do que eu
pergunte"*, com a suspeita de que o `coverage_ratio` estava barrando por falta de
certeza.

---

## 1. A causa raiz não era o RAG

O `coverage_ratio` já tinha sido removido em `69c10c8`, dois commits antes de a
investigação começar. Ele nunca chegou a rodar em produção:

- **`./ia` não é bind mount.** O `docker-compose.yml` monta apenas `./ia/logs`; o
  Dockerfile copia o código. Editar `ia/` no host não muda nada dentro do
  container até `docker compose up -d --build ia-service`. A imagem em execução
  tinha 44 horas e ainda continha o gate.
- **Depois virou 503 em tudo.** O banco compartilhado avançou para a migração
  `0006`, que não existia dentro daquela imagem, e o `ia-service` entrou em loop
  de restart (`Can't locate revision identified by '0006'`). A partir daí toda
  mensagem do chat respondia 503.

Nada disso aparecia na resposta do chat; aparecia só em
`docker compose logs ia-service`. Documentado em `CLAUDE.md`, seção Execução.

**Lição operacional:** mudança em `ia/` exige rebuild. Migração aplicada a partir
de arquivo não commitado quebra a máquina de todo mundo.

---

## 2. Estado depois do rebuild

Com o código correto rodando, sobre 8 perguntas numa reunião indexada de 21
chunks: **6 respondidas, 2 recusas**, e das 6 duas eram inúteis (uma pergunta
copiada da transcrição e uma resposta montada errado).

O threshold de similaridade **não** era o gargalo — 14 de 15 candidatos passavam
de 0.55. O gargalo era a seleção mandar **um trecho só** ao modelo.

---

## 3. Correções aplicadas

| # | Correção | Evidência que motivou |
|---|---|---|
| 1 | `_add_best_by_similarity`: o candidato de maior similaridade sobrevive ao rerank lexical quando a diferença passa de 0.10 | "O cliente falou sobre preço ou orçamento?" mandava o chunk 10 (sim 0.677, diz "orçamento" de passagem) e descartava o 9 (0.783), que é a conversa sobre orçamento x pedido |
| 2 | `_second_attempt`: recusa dispara uma releitura com 3 trechos e prompt diferente | 6/8 → 7/8 respondidas; "próximos passos" tinha as passagens já na primeira tentativa |
| 3 | `_is_question_echo`: resposta que é trecho literal da evidência e termina em "?" é rejeitada | "Quais produtos foram mencionados?" respondia com uma pergunta copiada do chunk 16, servida como resposta fundamentada |
| 4 | `_is_too_short`: menos de 4 palavras dispara releitura, mas **não veta** o resultado dela | "Sim.", "Preço.", "Estoque." viravam resposta final; trocar por "não encontrei" seria pior |
| 5 | `_citations_for`: citação recortada em `chat_citation_chars` (350) em volta da **resposta**, não da pergunta | a citação era o mesmo bloco de 2000 chars que o modelo lê — parede de transcrição sob uma resposta de uma linha |
| 6 | Prompt exige frase completa, com exemplo do que não serve | "Sim." → "Sim, o CRM tem API aberta." |
| 7 | `CHAT_TEMPERATURE=0.4` | decodificação gulosa (0.0) era o que produzia a resposta de uma palavra |
| 8 | Roteamento para os 13 campos de `final_summary` | "quais produtos" respondia "Produtos: Estoque" enquanto o campo já dizia `["TOTVS Backoffice - Linha Datasul"]` |
| 9 | `_is_unknown_answer` casa pelo radical `transcri` | o modelo escrevia "transcribção", escapava do detector e a recusa era servida **com citação anexada** |
| 10 | `_apply_quantity_anchor` descarta sentença que é só o número | `"15 lojas. 15"` → `"15 lojas."` |
| 11 | `_SELF_CONTAINED_TERMS = 3`: histórico só entra na busca quando a pergunta tem menos de 3 termos de conteúdo | histórico colado levava a consulta de 21 para 143 chars e "O CRM tem API aberta?" ia do chunk 16 para o 19 |
| 12 | Log em todos os caminhos: `chat_answer=served words=N chunks=[...] retried=X` e `chat_fallback=<razão> stage=...` | as quatro razões de fallback davam a mesma frase ao usuário e não apareciam em lugar nenhum; o diagnóstico dependia de contar tokens no log do Ollama |

### Roteamento por campo consolidado

Perguntas de agregação ("quais produtos", "qual o sentimento", "quem
participou") têm resposta melhor pronta em `final_summary`, produzida por todos
os chunks mais a consolidação mais, para `produto`, o casamento com o catálogo.
Recuperação top-k procura *o trecho que responde*, não *todos os trechos que
mencionam* — é o instrumento errado para essas perguntas.

O roteador é **léxico e ordenado** (primeiro que casa vence; `gap_produto` antes
de `produto` porque "o que falta no produto?" é lacuna, não catálogo). Medido:
**18/18 acertos, zero roteamentos falsos**.

Efeito: `"Quem participou?"` de 39s/"PESSOA" para **1s**/"gestor; gerente;
diretor". `"Quais produtos?"` de 42s/"Produtos" para **2s**/"TOTVS Backoffice -
Linha Datasul".

---

## 4. Hipóteses medidas e descartadas

Nove. Registradas aqui e em comentário no código para ninguém repetir.

| Hipótese | Resultado medido |
|---|---|
| Mandar 5 trechos em vez de 1 | "Qual o sentimento do cliente?" **recusou** com 5 e respondeu com 1 |
| 3 trechos de 700 chars | recusou |
| Exemplo (one-shot) no prompt de releitura | 2 recusas em 5 perguntas, com e sem temperatura |
| Lista de palavras de moldura no `_lexical_query` | 6/8 respondidas contra 7/8 sem a lista; derrubou o chunk que fala de produtos |
| Validar termos contra as passagens semanticamente próximas | não cortou nada na pergunta ruidosa e **esvaziou** a query de "Quantas máquinas precisam ser substituídas?" |
| Mesmo filtro no `excerpt_relevance_score` (rerank) | seleção piorou nas duas formulações |
| Limpar a pergunta antes de gerar o embedding | "boleto" caiu de 0.729 para 0.600; "cloud" perdeu o 1º lugar |
| Roteamento semântico contra `_CATEGORY_QUERY_GROUPS` | **2/8** ("quais produtos" → `feedback_produto`) |
| Roteamento semântico com descrições reescritas | **4/8** ("quais produtos" → `persona`); margens dos casos corretos sobrepostas às dos que não deviam rotear |

O padrão: o `nomic-embed-text` não resolve treze categorias de negócio próximas
em frase curta, e limpar a consulta encolhe o `ts_rank` a ponto de piorar a
ordenação. O ruído estava carregando algum sinal.

---

## 5. Correções que fiz em mim mesmo

**Modelo errado.** Afirmei que o chat rodava `qwen2.5:3b` porque li o default do
`config.py`. O `.env` sobrescrevia para `gemma3:1b`, e o qwen nem estava baixado.
O `CLAUDE.md` avisa que as variáveis do Compose têm precedência; eu não apliquei.

**"Alucinação" que não era.** Duas vezes chamei uma resposta de alucinada.
Conferindo palavra por palavra contra a evidência:

```
resposta: "importar um lead através de um formulário com perguntas e
           conversas do WhatsApp"
'formulario' na evidência? True   'pergunta' na evidência? True
'whatsapp'   na evidência? True
ausentes: ['atrave', 'importando', 'usuario']   <- só conectivos

resposta qwen: "buscar leads através de um mapa e adicionar ao catálogo"
'mapa' True   'catalogo' True   'workflow' True   'qualificacao' True
```

Não é invenção, é **montagem errada com peças verdadeiras**. Importa porque
nenhuma verificação lexical pega esse erro — e a guarda que existe (`_unsupported_numbers`)
cobre apenas números.

---

## 6. Modelo

Decisão do usuário: precisão acima de tempo.

`qwen2.5:3b` (3.1B, Q4_K_M, contexto 32768, 1.9 GB) substituiu `gemma3:1b` nos
três papéis — chat, chunk e consolidação.

| pergunta | gemma3:1b | qwen2.5:3b |
|---|---|---|
| "O cliente usa alguma ferramenta hoje?" | "Sim, o cliente usa alguma ferramenta." | "usam uma ferramenta **manual** para controle de inventário" |
| "Qual o principal desafio?" | "perde muito tempo com ferramentas manuais" | "o **controle do inventário**, que está levando muito tempo" |
| "Há quanto tempo atua no varejo?" | "atua no **varejismo**" (palavra inventada) | "atua há 10 anos no varejo" |
| latência típica | 11-25s | 22-38s (um caso de 126s) |

### Sobre contexto

O contexto **não estava mordendo**. Medido em 30 gerações: maior prompt 1564
tokens, **zero truncamentos**, 19% da janela de 8192. O que é pouco é quanto da
reunião chega ao modelo — no máximo 5 trechos de 2000 chars, ~6% de uma reunião
de 160 mil caracteres. Aumentar isso foi medido e **piorou** no 1B. Com o 3B vale
remedir antes de mexer em `CHAT_CONTEXT_LENGTH`.

---

## 7. Persistência da conversa

Antes: o histórico existia só no `payload` que o navegador reenviava. Recarregar
a página apagava a conversa, e duas abas na mesma reunião divergiam.

- **`ai.chat_messages`** (migração `0007`): `analysis_id`, `role`, `content`,
  `grounded`, `fallback_reason`, `seq`, `created_at`. FK com `ON DELETE CASCADE`,
  índice `(analysis_id, seq)`.
- **IA**: `GET /analises/{id}/chat` novo; o `POST` lê a conversa do banco e
  **ignora** o histórico que o cliente manda.
- **Backend**: `GET /api/dashboard/meetings/{id}/chat`.
- **Frontend**: `chatService.history()` e a tela carregando ao escolher a reunião.

Uma conversa por reunião. O servidor é a fonte da verdade.

### Três bugs que apareceram nesse trecho

1. **Ordem sorteada.** `now()` no Postgres é tempo da **transação** — pergunta e
   resposta gravadas no mesmo commit recebem o mesmo instante, e o desempate caía
   no `id`, que é UUID aleatório. A conversa voltava com a resposta antes da
   pergunta. Resolvido com coluna `seq` identity.
2. **Efeito dominó.** O saneador do histórico descartava aquela lista torta
   inteira, então a pergunta dependente seguinte perdia o contexto e recusava.
3. **`model_copy` não valida.** Injetava dicionários onde o schema espera objetos
   e ignorava a regra de alternância. Como `persist_turn` é deliberadamente
   tolerante (o usuário já tem a resposta na tela; perder o registro não pode
   virar 503), um turno meio-gravado deixaria dois `user` seguidos e a pergunta
   **seguinte** viraria 422 — a conversa salva quebrando o chat. Coberto por
   `conversation_history` e por teste que monta o cenário torto.

---

## 8. Como o churn é calculado hoje

Duas camadas, e a do modelo está desligada.

1. O LLM resume cada chunk em fatos por categoria; os de churn vão para
   `grouped["CHURN"]`. `_NON_CHURN_CANCELLATION_PATTERN` descarta cancelamento
   operacional ("pedido cancelado"), que é métrica, não conta saindo.
2. Os códigos que o modelo declara são **ignorados**: `trust_declared_motives =
   False`. O `config.py` registra o porquê — o 1B acertou 3 de 6 e, com espaço,
   declarava os cinco códigos e empurrava uma demo de CRM para churn 100 contra
   30 das regras.
3. `motive_rules.py` aplica regex por sentença: um motivo dispara quando um
   *trigger* casa e nenhum *blocker* casa, com trava de hipótese ("e se não der
   certo?", "por exemplo") — exceto ameaça de cancelamento, que tem
   `survives_hypothetical`.
4. `calculate_churn_risk` soma pontos fixos, sem repetir motivo, teto 100:
   AMEACA_CANCELAMENTO 50, INSATISFACAO_EXPLICITA 30, MENCAO_CONCORRENTE 25,
   RECLAMACAO_PRODUTO 15, INATIVIDADE_PROLONGADA 10.
5. `_score_reason` garante que score 0 nunca venha com motivo e score > 0 nunca
   venha com "nenhum sinal".

Churn 0 nas reuniões de teste é o desenho funcionando: são calls de prospecção,
não há cliente para perder.

---

## 9. Configuração em vigor

```
OLLAMA_MODEL=qwen2.5:3b            OLLAMA_CHUNK_MODEL=qwen2.5:3b
OLLAMA_CONSOLIDATION_MODEL=qwen2.5:3b   EMBEDDING_MODEL=nomic-embed-text
CHAT_TEMPERATURE=0.4               CHAT_CITATION_CHARS=350 (default no config)
CHAT_SIMILARITY_THRESHOLD=0.55     CHAT_MAX_EVIDENCE_CHARS=2000
CHAT_NUM_PREDICT=512               CHAT_CONTEXT_LENGTH=8192
```

Ollama: `MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1`, `FLASH_ATTENTION=1`,
`KV_CACHE_TYPE=q8_0`. Com um modelo residente por vez, cada pergunta troca entre
o embedding e a geração — esse vai-e-vem é a maior parte da latência percebida.

---

## 10. Aberto

- **`trust_declared_motives` continua `False`.** O comentário no `config.py` diz
  "turn on with a model that can classify", e agora existe um. Não foi medido.
- **Nenhuma análise reprocessada com o qwen.** Os campos de `final_summary` que o
  roteamento serve saíram do `gemma3:1b`. Rodar uma reunião ponta a ponta no
  modelo novo é o que mostra se a precisão melhorou onde mais importa — e vai
  demorar bem mais que os 132s de antes.
- **`chunk_motive_classification` e `ollama_chunk_num_predict=256`** foram
  calibrados para o 1B. Merecem remedição.
- **Código morto:** `scoring_service.infer_churn_motives` e
  `infer_opportunity_motives` são chamados **só por testes** (17 chamadas em
  `test_scoring_service.py`). Quem lê `scoring_service.py` acha que é ali que os
  motivos saem; a inferência real está em `motive_rules.py`.
- **O erro que sobra é de montagem, não de invenção**, e nenhuma verificação
  lexical o pega. Teto do modelo.
- **O portão de histórico não teve o ganho reproduzido.** Está correto por
  construção e não faz mal, mas na rodada final o cenário de controle acertou com
  e sem ele. Registrado sem vender como vitória.

---

## 11. Como depurar da próxima vez

```bash
docker compose logs -f ia-service | grep chat_
```

- `chat_answer=served words=6 chunks=[16] retried=False` — respondeu, com quantas
  palavras, de quais trechos, e se houve releitura.
- `chat_fallback=insufficient_evidence stage=retrieval candidates=15
  best_similarity=0.51 threshold=0.55` — nada passou do corte.
- `chat_fallback=insufficient_evidence stage=model_verdict retried=True` — o
  modelo recusou duas vezes com evidência na mão. Diagnóstico diferente,
  correção diferente.
