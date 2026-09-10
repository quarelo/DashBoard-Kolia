# Tratamento do Dataset de Transcrições — TOTVS Inteligência Comercial

## Visão Geral

Este documento descreve todas as etapas de tratamento aplicadas ao dataset de transcrições de reuniões comerciais da TOTVS antes de enviá-lo para análise pela IA. O arquivo original (`ANON_nome_transcricao.csv`, 45 MB, 334.502 linhas brutas) apresentava problemas estruturais graves que impediam qualquer ferramenta padrão (`pandas.read_csv`, `csv.reader`, Excel) de abri-lo corretamente. Além dos problemas de formato, o conteúdo das transcrições continha ruído significativo — fragmentação de diarização, small talk, aspas residuais — que degradaria a qualidade da análise.

O pipeline final (`pipeline_totvs.py`) executa 4 etapas em sequência: parsing do CSV malformado → deduplicação → merge de fragmentos + remoção de small talk → filtragem de reuniões inúteis. O resultado é um CSV limpo com 1.044 reuniões prontas para chunking e análise.

---

## Diagnóstico do Arquivo Original

Antes de qualquer tratamento, analisamos o arquivo byte a byte e identificamos os seguintes problemas:

O CSV estava malformado por um bug de "double-encoding": cada linha de dados havia sido envolvida em um par extra de aspas, como se a linha inteira (as 18 colunas juntas) fosse um único campo. Isso fez com que o campo `ANON_TRANSCRICAO` — que já era naturalmente quoted por conter vírgulas e quebras de linha — ficasse com aspas triplas e duplas sobrepostas. Um parser CSV padrão interpretava cada linha como 1 campo em vez de 18.

A ferramenta de diarização original havia colocado aspas em volta de algumas linhas de speaker (`"[LOCUTOR N]: texto"`), mas não de todas. Essas 1.168 aspas internas sobraram dentro do campo de transcrição e quebravam a estrutura CSV ainda mais, criando falsos delimitadores de campo.

O arquivo era quase todo UTF-8, mas continha 6 bytes Latin-1 soltos em posições onde a diarização havia inserido uma aspa no meio de um caractere multi-byte UTF-8, corrompendo a letra (por exemplo, `ê` virava um byte `0xaa` isolado). Todas as linhas usavam line endings Windows (`\r\n`).

---

## Etapa 1 — Parsing do CSV Malformado

Como nenhum parser padrão conseguia abrir o arquivo, construímos um parser customizado que lê os bytes brutos e reconstrói as linhas manualmente.

O parser identifica os limites de cada reunião pelo padrão `\r\n"DIGITOS,` (quebra de linha seguida de aspa e o ID numérico da próxima reunião). Para cada bloco entre dois limites, ele encontra os marcadores `""` que delimitam o campo `ANON_TRANSCRICAO` — verificamos que todas as reuniões têm exatamente 2 ocorrências de `""`, uma abrindo e outra fechando o campo. Os 10 campos antes da transcrição (de `ID_MEETING` até `DT_CRIACAO`) são extraídos por split simples de vírgula, e os 7 campos depois (de `UF` até `NOTA_NPS`) são extraídos do texto após o marcador de fechamento.

Todas as aspas dentro do campo de transcrição — tanto as do diarizador quanto as residuais do double-encoding — são removidas nesta etapa. Verificamos empiricamente que nenhuma delas carrega informação comercial: são artefatos de formatação, não conteúdo falado. O encoding é tratado com `errors='replace'`, aceitando a perda de 6 caracteres corrompidos em 46 milhões de bytes.

Esta etapa recuperou as 18 colunas corretamente para todas as 1.147 linhas, com zero erros de parse.

---

## Etapa 2 — Remoção de Duplicatas

Identificamos 37 grupos de reuniões duplicadas — mesma combinação de `CODT` (cliente), `DURACAO_MEETING` e `DT_CRIACAO`, com transcrições byte-a-byte idênticas (confirmado por hash MD5). Esses são registros da mesma reunião inseridos mais de uma vez no sistema.

Para cada grupo, mantemos a versão com a transcrição mais longa (na prática são idênticas, mas a regra garante que não perdemos conteúdo em caso de divergência futura). Foram removidas 52 linhas duplicadas.

Sem essa deduplicação, a IA contaria os mesmos sinais de churn e oportunidade em dobro, inflando scores artificialmente.

---

## Etapa 3 — Merge de Fragmentos de Diarização

Este foi o tratamento com maior impacto na qualidade do texto. O diarizador original fragmentava frases entre LOCUTORs diferentes com altíssima frequência: 38,7% de todos os turnos tinham no máximo 2 palavras, e 25,4% eram de uma única palavra. Uma reunião com 5-6 participantes reais gerava até 59 IDs de LOCUTOR distintos — a grande maioria sendo "fantasmas" criados por erro de segmentação.

Exemplos reais do problema antes do tratamento:

```
[LOCUTOR 102]: Eu ia at
[LOCUTOR 54]:  perguntar se era o novo uniforme

[LOCUTOR 15]:  tá todo
[LOCUTOR 3]:   mundo te olhando, porque era eu que ia apresentar.

[LOCUTOR 47]:  que
[LOCUTOR 3]:   é uma prioridade pra nós
```

O merge opera em duas sub-etapas. Primeiro, turnos consecutivos do mesmo LOCUTOR são sempre concatenados — não há razão para o mesmo speaker ter dois turnos seguidos sem ninguém falando no meio. Segundo, turnos curtos (até 5 palavras) que não terminam com pontuação de fim de frase (`.?!:`) e são seguidos por um turno que começa com letra minúscula são identificados como fragmentos da mesma frase cortada pelo diarizador. Esses fragmentos são fundidos, e o turno resultante é atribuído ao speaker que contribuiu mais palavras na cadeia — uma heurística local que acerta o speaker real na maioria dos casos.

O merge reconhece e preserva respostas curtas que são utterances completas ("Sim.", "Não.", "Exato", "Ok", "Pois é" etc.) — estas não são fundidas no turno anterior, mesmo sendo curtas.

Resultados do merge no dataset completo:

- Turnos originais: 325.527
- Turnos após merge: 186.150 (redução de 42,8%)
- Cross-speaker merges realizados: 139.297
- LOCUTORs por reunião (média): 21,9 → 16,2

A proporção de turnos de 1-2 palavras caiu de 38,7% para 9,0%.

---

## Etapa 4 — Remoção de Small Talk

Remove turnos inteiros que são ruído social sem valor comercial. Opera em modo conservador: só remove um turno se ele inteiro bater com um padrão fixo, nunca corta pedaço de dentro de um turno maior. Isso é proposital — como a diarização vem fragmentada, é mais seguro pecar por remover pouco do que arriscar apagar contexto comercial no meio de uma frase cortada.

Categorias removidas:

- Cumprimentos e despedidas: "Boa tarde", "Tchau", "Até mais", "Obrigado"
- Confirmações de áudio: "Está me ouvindo?", "Conseguem me ouvir?"
- Turnos vazios: sem texto após o marcador `[LOCUTOR N]:`
- Turnos só com placeholder: texto que ficou apenas com `[PESSOA]`, `[EMPRESA]` ou `[LOCAL]` após a anonimização, sem conteúdo real

Tangentes longas (como histórias pessoais, papo sobre cadeira quebrando em apresentação, problemas com notebook) não são removidas por esta etapa — testamos um modo agressivo baseado em palavras-chave e ele cortou contexto comercial por coincidência de vocabulário. Esse tipo de limpeza semântica fica para o modelo de IA na etapa de análise por chunk, onde há contexto suficiente para distinguir anedota pessoal de conteúdo de negócio.

O merge de fragmentos é executado antes do small talk de propósito: fragmentos juntos formam frases que o classificador reconhece melhor. Por exemplo, "Boa" sozinha não bate em nenhum padrão, mas após o merge "Boa tarde, pessoal." é corretamente classificada como cumprimento.

Total de turnos removidos: 7.702.

---

## Etapa 5 — Filtragem de Reuniões Inúteis

Remove reuniões que não gerariam insight comercial:

- Reuniões sem transcrição (campo vazio): resultado de gravações que falharam ou reuniões canceladas que ficaram no sistema
- Reuniões com transcrição menor que 500 caracteres após toda a limpeza: conteúdo insuficiente para análise (tipicamente reuniões de menos de 1 minuto, testes de áudio, ou entradas acidentais)

Todas as 1.147 reuniões no dataset já tinham status `COMPLETED`, então não foi necessário filtrar por status.

Total removido nesta etapa: 51 reuniões (48 sem transcrição + 3 abaixo do threshold).

---

## Tratamento de Tags de LOCUTOR Embutidas

Durante a análise identificamos 6.625 linhas no arquivo original com tags `[LOCUTOR N]:` embutidas dentro do texto de outro turno, como `[LOCUTOR 49]: [LOCUTOR 4]: bom, vamos lá.`. Esse problema foi resolvido automaticamente pelo pipeline existente sem código adicional: a função de split de turnos quebra em todas as ocorrências de `[LOCUTOR N]:` (incluindo as embutidas), transformando o tag interno num turno separado. O turno vazio que sobra antes do tag embutido é removido pelo small talk cleaner como "turno vazio".

---

## Resultado Final

| Métrica | Antes | Depois |
|---|---|---|
| Arquivo | Ilegível (CSV malformado) | CSV válido, `pd.read_csv()` direto |
| Reuniões | 1.147 | 1.044 |
| Duplicatas | 52 | 0 |
| Turnos de fala | 325.527 | ~178.448 |
| Turnos de 1-2 palavras | 38,7% | 9,0% |
| LOCUTORs/reunião (média) | 21,9 | 16,2 |
| Aspas residuais | 2.215 | 0 |
| Caracteres de transcrição | 42.515.202 | 38.743.708 |
| Redução total | — | 8,9% |
| Menor transcrição | 0 (vazia) | 507 chars |
| Maior transcrição | 183.498 chars | 176.549 chars |

O CSV de saída tem 18 colunas corretamente separadas, transcrições com frases coerentes no formato `[LOCUTOR N]: texto`, e está pronto para entrar na etapa de chunking com overlap e análise pelo modelo local.

---

## Arquivos Produzidos

- `transcricoes_limpas.csv` — dataset tratado, pronto para a IA
- `pipeline_totvs.py` — script Python com o pipeline completo, reproduzível com `python pipeline_totvs.py caminho/do/csv/original.csv caminho/de/saida.csv`

COLUNAS
Campo	Significado
ID_MEETING	Número de identificação da agenda (única por reunião)
DT_MEETING	Data/hora da reunião
FORMATO_MEETING	Descrição formato da reunião. Valores possíveis: Vídeo, Áudio, Presencial e VoIP (LINK).
ID_STATUS_MEETING	Identificador status da reunião
STATUS_MEETING	Status da reunião
DURACAO_MEETING	Duração da reunião formato HH:MM:SS
CODT	Código do cliente/ lead/ prospect/ suspect
TP_RECURSO	Classificação do cliente lead/customer
FLG_EXTERNO	Flag reunião externa
DT_CRIACAO	Data/ hora criação reunião
ANON_TRANSCRICAO	Detalhes da transcrição da reunião (Anonimizado)
UF	Unidade Federativa (Estado) de localização do cliente
CNAE	Código da Classificação Nacional de Atividades Econômicas da empresa
NOME_UNIDADE	Nome da unidade de venda que se encontra o cliente
NOME_SEGMENTO	Segmento de mercado ou atuação comercial do cliente
FAIXA_FATURAMENTO_CLIENTE_EC	Classificação da faixa de faturamento estimada ou declarada do cliente
DT_ULTIMA_PESQUISA	Data da resposta da última pesquisa de satisfação do cliente
NOTA_NPS	Nota do Net Promoter Score (NPS) atribuída pelo cliente na pesquisa de satisfação
