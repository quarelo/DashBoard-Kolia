# Enriquecimento de metadados — campos do CSV na análise e no dashboard

Data: 2026-09-10. Classificação dos 16 campos de metadados do dataset TOTVS
em três categorias: contexto para o prompt da IA, filtros de dashboard e
campos armazenados sem uso ativo. O objetivo é que a IA produza análises mais
precisas quando sabe quem é o cliente, e que o diretor comercial consiga
fatiar o dashboard pelas dimensões que importam.

Os dois campos obrigatórios do CSV (`ID_MEETING` → `external_id`,
`ANON_TRANSCRICAO` → `transcription`) não entram nesta classificação — eles
já tinham destino próprio no schema. Os 16 restantes são armazenados no campo
JSONB `core.meetings.source_metadata` pelo parser de importação, que é
agnóstico a colunas: qualquer nome que não seja `ID_MEETING`,
`ANON_TRANSCRICAO` ou `TITLE` vira chave/valor no JSON.

---

## Campos enviados ao prompt da IA (5)

Estes campos são extraídos pelo backend (`ia_gateway._analysis_metadata`) e
enviados à IA no campo `metadata` do `POST /analisar`. A IA os persiste em
`ai.meeting_analyses.source_metadata` e os injeta como bloco `CONTEXTO
COMERCIAL DA REUNIÃO` nos prompts de análise por chunk e de consolidação.

| Campo | Label no prompt | Por que vai para a IA |
|---|---|---|
| `TP_RECURSO` | Tipo de cliente | Muda a lente inteira da análise. Reunião com lead é prospecção — a IA busca objeções, sinais de compra, próximo passo. Com customer é retenção — busca insatisfação, risco de churn, oportunidade de upsell. Sem essa distinção, a IA analisa os dois cenários do mesmo jeito e perde o ponto central. |
| `NOME_SEGMENTO` | Segmento de mercado | Dá contexto de vocabulário e negócio. "Módulo fiscal" numa reunião de varejo tem peso diferente de uma reunião de agronegócio. A IA calibra o que é dor real do cliente versus conversa genérica do setor. |
| `FAIXA_FATURAMENTO_CLIENTE_EC` | Faixa de faturamento | Indica o porte do negócio. Cliente de faixa alta com problema é alerta vermelho — o impacto comercial de perdê-lo é maior. Cliente de faixa baixa explorando funcionalidades é oportunidade de crescimento. Sem isso, a IA trata todo cliente como se tivesse o mesmo peso. |
| `NOTA_NPS` | NPS do cliente | A nota muda a interpretação do texto. NPS 3 com menção a "concorrente" na transcrição é churn iminente. NPS 9 com a mesma menção é só comparação saudável. A combinação do número com o conteúdo da fala produz um risco de churn muito mais calibrado do que qualquer um dos dois sozinhos. |
| `DURACAO_MEETING` | Duração da reunião | Reunião de 8 minutos que deveria ser de 30 indica desengajamento ou problema resolvido rápido. Reunião de 2 horas indica negociação complexa. A duração dá contexto sobre a profundidade da conversa e ajuda a IA a pesar a relevância do que foi dito. |

### Instruções ao modelo

O bloco de contexto é injetado no início do prompt com duas instruções
explícitas:

1. **Use o contexto para calibrar, não para repetir.** O modelo não deve
   copiar "Tipo de cliente: lead" nos pontos-chave — a informação serve como
   lente de interpretação, não como fato extraído da transcrição.
2. **Combinações importam.** NPS baixo + menção a concorrente = churn
   iminente. Lead + pergunta sobre preço = oportunidade quente. O modelo é
   instruído a cruzar o contexto com o conteúdo da fala.

### Retrocompatibilidade

O campo `metadata` é opcional no `AnalyzeRequest`. Análises disparadas sem
metadados (reuniões importadas antes desta mudança, ou CSVs sem essas colunas)
funcionam exatamente como antes — o bloco de contexto simplesmente não aparece
no prompt.

---

## Campos usados como filtro de dashboard (5)

Estes campos **não vão para o prompt** — eles não mudam a interpretação da
transcrição pela IA, mas são essenciais para o diretor comercial fatiar e
comparar os resultados. São expostos como query parameters em
`GET /api/meetings` e os valores distintos disponíveis são listados por
`GET /api/meetings/filters`.

| Campo | Param da API | Como filtra | Por que é filtro e não contexto |
|---|---|---|---|
| `UF` | `?uf=SP` | Match exato | O estado do cliente não muda como a IA interpreta uma frase, mas o diretor quer comparar desempenho regional ("Como está o Nordeste vs. Sudeste?") e alocar time por região. |
| `NOME_UNIDADE` | `?unidade=porto` | Contém, case-insensitive | O nome da unidade comercial é informação organizacional interna. Não altera a análise da conversa, mas responde "Qual unidade está convertendo mais?" — gestão de equipe. |
| `FORMATO_MEETING` | `?formato=Vídeo` | Match exato, case-insensitive | O formato (Vídeo, Áudio, Presencial, VoIP) é dado operacional. Não muda o conteúdo da fala, mas o diretor quer saber se reunião presencial converte mais que vídeo — ROI de deslocamento. |
| `DT_MEETING` | `?dt_meeting_from=2025-01-01&dt_meeting_to=2025-06-30` | Range de string (YYYY-MM-DD) | A data permite análise temporal — tendências, sazonalidade, "esse trimestre vs. anterior". Para a IA, a data da reunião não agrega: ela analisa o que foi dito, não quando. |
| `CNAE` | `?cnae=4751201` | Match exato | O código de atividade econômica é útil para concentração de carteira ("Estamos muito expostos a um setor?"). É um código numérico que não dá contexto semântico à IA — o `NOME_SEGMENTO` já cobre essa dimensão de forma legível. |

### Endpoint de filtros

`GET /api/meetings/filters` retorna os valores distintos de cada dimensão para
popular dropdowns no frontend:

```json
{
  "uf": ["MG", "PR", "RJ", "SP"],
  "segmento": ["Construção", "Logística", "Varejo"],
  "unidade": ["Porto Alegre", "São Paulo"],
  "formato": ["Áudio", "Presencial", "Vídeo", "VoIP"],
  "cnae": ["4751201", "6201501"]
}
```

### Onde os metadados aparecem hoje

- Os mesmos filtros existem em `GET /api/dashboard/overview`, `/executive` e
  `/meetings`, que leem `ai.meeting_analyses` com `LEFT JOIN core.meetings`.
- A página da reunião mostra os 16 campos numa grade, lidos de
  `core.meetings.source_metadata`. Uma análise enviada direto à IA, sem passar pelo
  import, não tem essa linha. Ela aparece sem grade e sem transcrição, e só o
  diretor comercial a exclui, mesmo com os 5 campos de contexto guardados em
  `ai.meeting_analyses.source_metadata`.

---

## Campos armazenados sem uso ativo (6)

Estes campos ficam salvos no `source_metadata` JSONB, mas não são enviados à
IA nem expostos como filtro. A razão é a mesma para todos: não agregam valor
nem à interpretação da transcrição nem ao recorte que um diretor comercial
faria no dashboard.

| Campo | Por que não é usado |
|---|---|
| `ID_STATUS_MEETING` | Código numérico interno redundante com `STATUS_MEETING`. É a chave primária de uma tabela de domínio do sistema de origem, sem significado fora dele. |
| `STATUS_MEETING` | Dado operacional da agenda (COMPLETED, IN_PROGRESS). No dataset tratado todas as reuniões são COMPLETED — foi critério de seleção do pipeline de tratamento. Mesmo que houvesse variação, o status da agenda não muda o conteúdo da conversa nem o que o diretor quer filtrar. |
| `FLG_EXTERNO` | Flag booleana de sistema ("reunião externa"). Sem definição clara do que "externa" significa no contexto comercial da TOTVS — pode ser presencial fora do escritório, pode ser com participante externo. Ambíguo demais para servir de filtro confiável ou contexto para a IA. |
| `DT_CRIACAO` | Data de criação do registro no sistema de agendamento. É diferente de `DT_MEETING` (data real da reunião). Para análise temporal o que importa é quando a reunião aconteceu, não quando alguém criou o agendamento. Guardar as duas datas serve para auditoria, mas filtro e contexto usam `DT_MEETING`. |
| `CODT` | Código interno do cliente no sistema da TOTVS. Útil para join com sistemas legados ou CRM, mas é um identificador opaco — não dá informação semântica à IA e não é uma dimensão que o diretor filtraria (ele filtra por segmento, UF e faturamento, não por código). |
| `DT_ULTIMA_PESQUISA` | Data da última pesquisa NPS. O que importa para a análise é a nota (`NOTA_NPS`), não quando ela foi coletada. A data da pesquisa seria relevante para avaliar a "frescura" do NPS, mas isso exigiria lógica de validade temporal que não existe no pipeline atual. |

### Por que armazenar mesmo sem usar

Todos os 16 campos ficam no JSONB por três razões:

1. **Custo zero de armazenamento marginal.** O parser já salva qualquer
   coluna extra sem código adicional — não armazenar exigiria um filtro
   explícito, que é mais código e mais manutenção.
2. **Consulta ad hoc.** Um `SELECT source_metadata->>'CODT' FROM
   core.meetings WHERE ...` funciona direto para quem precisar fazer um join
   manual ou uma exportação.
3. **Decisão reversível.** Se amanhã o `FLG_EXTERNO` ganhar significado
   claro, promovê-lo a filtro de dashboard é uma linha no endpoint; se o
   `DT_CRIACAO` virar relevante, injetá-lo no prompt é uma linha no
   `_CONTEXT_LABELS`. Não ter o dado obrigaria a re-importar o CSV.
