# Página de Produto — dados de apoio

Data: 2026-09-29, revisto em 2026-10-01. Dados de uma tela dedicada por produto,
que abre a partir de uma barra do Gráfico de Produto do dashboard executivo
(`ai.meeting_analyses.final_summary`, ver `backend/CLAUDE.md` → "Dashboard").

- **Saúde do produto mês a mês** — reclamações, gaps e elogios ao longo do
  tempo, não só a foto do período filtrado.
- **Produto × persona** — quem, profissionalmente, fala desse produto nas
  reuniões.
- **Natureza dos gaps** — em que tipo de lacuna os gaps daquele produto caem.
- **Qualidade do produto contra o portfólio** — cinco métricas por reunião, cada
  uma ao lado da média (`/products/{nome}/quality`).
- **Gap × catálogo** — quais gaps já têm produto TOTVS que resolve
  (`/products/{nome}/gap-coverage`, o único que passa pela IA).

Ficaram de fora por agora, por decisão explícita: uma ficha-resumo automática do
produto e um ranking de reclamações por severidade (peso do `risco_churn` da
reunião). Nenhuma das duas foi implementada.

## O que a quebra por UF/segmento/CNAE era, e por que saiu

A primeira versão tinha três cards de segmentação — `por_uf`, `por_segmento`,
`por_cnae` — com a contagem de reclamação/gap/elogio em cada recorte. Saíram em
2026-10-01, da resposta e da tela.

O motivo é o denominador. Medindo a carga: 85 produtos distintos, e a **mediana
de reuniões detalhadas por produto é 1** — 27 dos 46 produtos que têm alguma
reunião de produto único têm exatamente uma, e 43 dos 85 têm uma menção só. Os
três cards de segmentação e o gráfico mensal eram, então, a mesma contagem
desenhada quatro vezes, três delas com uma barra. Não era falta de variedade de
forma: era um fato só, replotado.

As três leituras que entraram no lugar trocam o denominador em vez da forma:

- `natureza_gaps` conta **itens** (391 gaps na carga, mediana de 3 por produto,
  máximo 22), não reuniões.
- `/quality` compara contra o **portfólio inteiro** (94 reuniões de produto
  único), e uma comparação ainda informa com n=1, ao contrário de uma série.
- `/gap-coverage` cruza com uma fonte **de fora das reuniões**: os 302 produtos
  de `ai.products`, com embedding.

Se a quebra por UF/segmento voltar a ser pedida, o `git` tem o código; o que não
deve voltar é ela ocupando três cards.

## Endpoint

```
GET /api/dashboard/products/{nome}/insights
```

Mesmos filtros de query que `/overview`, `/executive` e `/products/{nome}/meetings`
(`uf`, `segmento`, `unidade`, `formato`, `cnae`, `dt_meeting_from`, `dt_meeting_to`),
aplicados a `core.meetings.source_metadata` antes de qualquer agregação —
implementado em `services/analysis_read.py::product_insights`, roteado em
`routers/dashboard.py`.

`nome` é o texto exato de `final_summary.produto` (o mesmo nome que já aparece
em `top_produtos` no `/executive` e que `/products/{nome}/meetings` usa). Um
nome que não bate com nenhum produto citado não é erro: a resposta volta com
`reunioes_detalhadas: 0` e todas as listas vazias, igual ao comportamento já
existente em `product_meetings` — leitura pura, sem validação contra um
catálogo à parte.

O recorte por produto é um `WHERE` em SQL (`final_summary -> 'produto' @>
jsonb_build_array(:produto)`), não um `continue` em Python depois de varrer a
tabela. A condição é de propósito a mais frouxa das duas — "cita o produto",
sem exigir que o cite sozinho — justamente para ser um superconjunto do que a
regra de produto único aceita; a regra em si continua em Python, onde está
documentada. Medido com 201 análises: 110 ms por chamada varrendo tudo contra
10 ms com o `WHERE`, e das 201, 60 não citam produto nenhum. Não há índice GIN
em `final_summary` — criá-lo seria migration do serviço de IA, dono do schema
`ai`; a 1044 reuniões vale medir se compensa.

## A regra de produto único (por quê os números aqui não somam com `mencoes_produto_mais_citado`)

Os três blocos usam a **mesma aproximação já assumida em `executive_overview`
e `product_meetings`**: uma reunião só entra no cálculo quando
`final_summary.produto` tem exatamente um item, e esse item é o produto
pedido. O motivo não mudou desde que foi documentado lá — `problemas_identificados`,
`gap_produto`, `feedback_produto` e `persona` são fatos no nível da reunião
inteira, não etiquetados por produto; numa reunião que cita dois ou mais
produtos não há como saber qual fato pertence a qual. Manter a mesma regra
aqui é o que garante que o número que aparece na Página de Produto bate com o
número que já aparece no Gráfico de Produto do executivo, em vez de abrir uma
segunda fonte de verdade com critério diferente.

Consequência prática: `reunioes_detalhadas` (o denominador de tudo neste
endpoint) é sempre menor ou igual a `mencoes_totais`, porque aquele número conta
toda menção, inclusive em reunião multi-produto. Um produto muito citado em
conjunto com outros pode ter uma barra grande no executivo e poucos dados aqui
— isso é esperado, não um bug. Na carga atual a diferença é grande: `TOTVS RH
Folha de Pagamento - Linha Protheus` tem 7 menções e 1 reunião detalhada.

`mencoes_totais` é a única exceção à regra de produto único neste endpoint, e
existe aqui para a Página de Produto se resolver com duas chamadas em vez de
três. Antes a tela lia esse KPI de `executive.top_produtos`, o que custava
agregar as 201 análises inteiras por um número — e dava "—" para todo produto
fora do Top 10, que aquela lista corta. O valor bate com
`top_produtos[].mencoes` do `/executive` para os mesmos filtros (conferido nos
10 do Top 10 e nos 85 produtos distintos da carga atual).

## Resposta

```json
{
  "produto": "TOTVS Backoffice - Linha Datasul",
  "mencoes_totais": 25,
  "reunioes_detalhadas": 18,
  "saude_mensal": [
    { "mes": "2026-06", "reunioes": 4, "reclamacoes": 2, "gaps": 1, "elogios": 3 },
    { "mes": "2026-07", "reunioes": 6, "reclamacoes": 5, "gaps": 3, "elogios": 1 }
  ],
  "natureza_gaps": [
    { "categoria": "Integração", "ocorrencias": 7 },
    { "categoria": "Automação de fluxo", "ocorrencias": 7 },
    { "categoria": "Não classificado", "ocorrencias": 3 }
  ],
  "personas": [
    { "nome": "Diretor Financeiro", "ocorrencias": 6 },
    { "nome": "Gerente de TI", "ocorrencias": 4 }
  ]
}
```

### `saude_mensal`

Uma linha por mês em que houve pelo menos uma reunião do produto, ordenada
cronologicamente. `mes` é `DT_MEETING` truncado pra `YYYY-MM` — mesma extração
de `_month_key` usada no comparativo mensal do `/executive`, então herda a
mesma limitação: só reconhece data em ISO (`YYYY-MM-DD`); outro formato fica
fora do agrupamento em vez de inventar um mês. `reclamacoes`/`gaps`/`elogios`
são contagens de itens (não de reuniões) dentro do mês, pela mesma regra do
Gráfico de Produto.

### `natureza_gaps`

Em que tipo de lacuna cada gap do produto cai, ordenado por volume, com
`Não classificado` sempre por último. Conta **itens**, não reuniões.

A classificação é **léxica**, não por embedding: `_GAP_NATURE_RULES` em
`services/analysis_read.py` é uma lista de dez categorias com o vocabulário de
cada uma, e as categorias saíram da contagem de palavras dos 391 gaps da carga
(`integração` 79, `ausência`/`falta` 138, `automação`/`automática` 80, `nativa`
36, `controle` 28) — derivadas do dado, não adivinhadas. Léxico porque roda sem
chamar modelo: a tela abre em ~70 ms e uma passada de embedding por gap custaria
52 ms cada, com o Ollama quente.

Medida nos 391 gaps, a taxonomia cobre **85,2%**. Rótulo único por gap (ganha a
categoria com mais ocorrências de vocabulário; empate pela ordem da lista, que é
por isso que `Integração` vem antes de `Financeiro` — "integração do meio de
pagamento" é gap de integração), então a soma das fatias fecha com o total de
gaps. Os 14,8% restantes aparecem como `Não classificado` em vez de serem
escondidos ou forçados numa categoria: é resíduo heterogêneo de verdade ("Falta
de líder de produção definido na empresa") e inclui extração ruim da IA — a
string "Nenhum gap identificado no portfólio TOTVS." veio gravada *como* um gap.
O tamanho dessa fatia é o aviso de que a regra não pega tudo.

### `personas`

Contagem de ocorrência de cada persona (`final_summary.persona`) nas reuniões
detalhadas do produto, ordenada por frequência. Uma reunião pode listar mais
de uma persona; cada uma soma separadamente.

## `GET /api/dashboard/products/{nome}/quality`

Cinco médias sobre as reuniões de produto único, cada uma ao lado da média do
portfólio: `risco_churn`, `oportunidade`, `satisfacao` (% de reuniões com
sentimento positivo), `gaps_por_reuniao` e `duvidas_por_reuniao`. As duas
primeiras saem de `risco_churn.score` e `score_oportunidade.score`, que estão em
100% das análises e não apareciam em nenhum lugar desta tela; `duvidas_em_aberto`
está em 99% e também não era lido.

A base de comparação é a **mesma população do numerador** — reuniões que citam um
produto só, sob os mesmos filtros. Se fosse o conjunto todo, a média incluiria
reunião multi-produto e de produto nenhum, e a diferença mediria isso em vez de
medir o produto.

`reunioes` e `reunioes_portfolio` vêm sempre na resposta porque a tela precisa
avisar quando o número sai de uma reunião só, o que é o caso mediano. Cada
métrica carrega `maior_e_melhor`: a barra divergente precisa saber de que lado
está o bom, já que 10 pontos acima da média é ótimo em oportunidade e péssimo em
risco de churn.

É a única leitura da tela que varre o portfólio inteiro e não é recortada por
produto — ~0,14 s nas 201 análises, agora que a transcrição saiu do
`_BASE_SELECT`.

## `GET /api/dashboard/products/{nome}/gap-coverage`

Quais gaps apontados neste produto já têm produto no catálogo TOTVS. Cross-sell
quando sim, pauta de roadmap quando não.

Atravessa os dois serviços porque nenhum dos dois consegue sozinho: o recorte
("os gaps deste produto, sob estes filtros") depende de `core.meetings`, que a IA
não lê, e o casamento depende de embedding e de `ai.products`, que o backend não
toca. Então `analysis_read.product_gap_texts` recorta, o roteador manda os textos
para `POST /produtos/gaps-catalogo` na IA, e `ia/src/app/services/gap_coverage_service.py`
casa. Sem gap nenhum o backend responde vazio sem chamar a IA.

**O critério é a margem, não a distância.** Medido nos 354 gaps distintos contra
os 302 produtos: a distância ao vizinho mais próximo é comprimida demais para
discriminar (p5 0,233, mediana 0,293, p90 0,339), porque texto de gap e descrição
de produto são os dois prosa comercial em português e o cosseno mede sobretudo
isso. Com um corte absoluto em 0,25 sobram 11% dos gaps e vários estão errados
("Ausência de banco de talentos online" → *TOTVS Central do Cliente*).

A margem entre o 1º e o 5º vizinho separa: margem baixa quer dizer que o catálogo
inteiro está equidistante, ou seja, que não há match. Nos 12 gaps de maior margem
a inspeção manual deu 12 acertos (chatbot → *Chat Commerce by Chatbot Maker*, PIX
→ *Recebe+ Conciliado Techfin*); nos 8 de menor, 8 rejeições corretas ("Falta de
líder de produção definido na empresa" → *Clima e Engajamento*, margem 0,006).
Limiares em `gap_coverage_likely_margin` 0,055 e `gap_coverage_possible_margin`
0,030, com teto de sanidade `gap_coverage_distance_ceiling` 0,32 (o p80), que
rejeita margem alta com o vizinho longe mesmo assim. Distribuição resultante na
carga, com a faixa do meio ligada: **7,6% provável, 27,4% possível, 65% sem
cobertura**; desligada, os 27,4% viram sem cobertura.

Daí os rótulos serem "provável" e "possível", nunca "coberto": a resposta sempre
devolve o nome, a URL e a distância, e a decisão é de quem lê. Em
`sem_cobertura` a lista de produtos vem vazia de propósito — não se mostra
palpite ao lado de um rótulo que diz que não há match.

### A faixa do meio está desligada

`gap_coverage_possible_enabled = False` desde 2026-10-01. O que cairia na faixa
do meio conta como `sem_cobertura`, sem produto sugerido.

O que a derrubou foi um caso visto na tela: para o gap *"Ausência de
funcionalidade nativa para visualizar informações de carga e histórico de entrega
no CRM padrão (requer dashboards personalizados)"*, do **TOTVS CRM Gestão de
Clientes**, a sugestão foi **App Meu Controle Fitossanitário** (margem 0,0324,
passando raspando do corte de 0,030). O catálogo tem as respostas certas —
`App Meu Rastreamento de Entregas`, `TOTVS Coleta e Entrega`, `TOTVS Roteirização
e Entregas` — e nenhuma apareceu nos 12 primeiros.

Uma sugestão errada ao lado de um produto não é neutra: ela faz quem lê
desconfiar do card inteiro, inclusive das sugestões da faixa de cima, que deram
12 de 12 na inspeção manual. Com a faixa desligada, o *TOTVS CRM* passa de 8
itens listados para 2, e o *TOTVS Gestão de Receitas* fica com 3 (PIX → *Recebe+
Conciliado Techfin*, do tipo que o gráfico existe para encontrar).

**O que religá-la exige.** O problema não é o limiar, e a primeira hipótese —
que a moldura de reclamação do gap dominava o vetor — foi **medida e descartada**:
cortar os começos repetidos (`Ausência de`, `Falta de`, `funcionalidade nativa
para`…) remove 22% do texto dos 354 gaps e não move a distribuição (mediana de
distância 0,293 → 0,293; de margem 0,026 → 0,026).

O lado errado era o do produto. `ai.products.embedding` é construído de
`name + description`, e as descrições são marketing de parágrafos inteiros que se
parecem todas ("O aplicativo Meu X foi desenvolvido especialmente para dar
mobilidade às principais rotinas…") — elas afogam o nome, que é a parte que diz
o que o produto faz. Buscando o mesmo gap contra **só o nome** dos 302 produtos,
os quatro de entrega do catálogo ocupam as quatro primeiras posições, com folga
clara para o quinto (0,3253 → 0,3588).

Então a ordem é: (1) buscar contra o nome do produto, (2) recalibrar as margens,
que mudam de patamar, e só então (3) religar o interruptor. Note que trocar o
vetor armazenado em `ai.products.embedding` afetaria também
`product_service.ground_products`, que identifica o produto da reunião no
pipeline de análise — a cobertura de gap precisa de um índice próprio por nome
(em memória, ~1,8 MB) ou de uma coluna `name_embedding` por migration.

Isto corrige o que a versão anterior deste documento afirmava em "O que não está
aqui": matching gap↔catálogo não estava bloqueado por falta de fonte de dado. O
*catálogo* existe e está vetorizado; o que não existe é *roadmap*, que é outra
coisa.

### Custo

É a chamada mais lenta da tela, e a única que depende do Ollama. Embeddar um gap
custa ~52 ms com o modelo quente e ~9 s a frio (carga do modelo), e um produto
chega a 22 gaps. Por isso `gap_coverage_service` mantém um **cache de embedding
em processo**, endereçado pelo texto: medido, a mesma chamada cai de 3,67 s para
0,33 s, e o piso de 0,33 s é a busca vetorial em si (uma por gap, sobre 302
produtos). Um produto novo, com o Ollama já quente, custou 0,68 s para 15 gaps.

O cache é em memória e não em tabela: os 354 gaps distintos da carga ocupam
~2,6 MB de vetor, e uma tabela exigiria migration no schema `ai`. Esvazia no
restart do `ia-service`. Se a persistência passar a importar, o passo seguinte é
uma tabela endereçada por hash do texto — e ela, por não ser ligada a análise
nenhuma, **não** entraria em `AI_ROWS_BY_ANALYSIS` (ver a exceção de exclusão de
reunião no `CLAUDE.md` da raiz).

No frontend este card carrega **fora** do `Promise.all` do resto da página, com
loading próprio: junto com as outras chamadas, a página inteira voltaria a
esperar pelo pior caso. Erro aqui também não derruba a tela — o resto é leitura
pura do banco e já está renderizado.

## O que não está aqui

- **Ficha automática** (resumo com top reclamações/gaps/elogios como texto,
  citações literais de `evidencias`) — não implementada nesta rodada.
- **Ranking de severidade** (reclamação pesada pelo `risco_churn` da reunião
  em que apareceu) — não implementada nesta rodada. Os números de
  `risco_churn`/`score_oportunidade` já existem por reunião em
  `ai.meeting_analyses.final_summary`; o que falta é só a agregação.
- **Cruzamento com concorrente**, **NPS por produto**, **matching semântico
  gap↔roadmap** — avaliados e descartados ou adiados em conversas
  anteriores (concorrente: fora de escopo por decisão do time; roadmap:
  não existe fonte de dado — note que gap↔**catálogo** foi implementado, ver
  acima, porque o catálogo existe e o roadmap não; motivo de churn por código: o código
  (`AMEACA_CANCELAMENTO` etc.) é descartado em `analysis_service.py` depois
  de gerar o score, não é persistido em `final_summary`).
