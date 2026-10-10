# Plano: recalibrar churn e oportunidade, com pontuação configurável

Data: 2026-10-09. Os scores de churn e oportunidade saturam: a maioria das
reuniões bate o teto ou encosta nele, e o número deixou de separar reunião boa de
reunião morna. Este documento registra o diagnóstico medido, o que foi simulado e
os passos para corrigir — incluindo tornar os pesos editáveis pelo time comercial,
com nomes legíveis na interface.

**Estado em 2026-10-09:** passos 2 a 7 implementados; o passo 1 (conjunto
rotulado) foi descartado e o passo 8 (recálculo) não rodou. Nenhuma análise foi
reprocessada. O que isso quer dizer na prática está na seção 6.

---

## 1. Diagnóstico

Medido em 2026-10-09 sobre o banco em uso: 198 análises com `final_summary` em
`DONE`/`DASHBOARD_READY` e 926 chunks com `chunk_summary`.

| Sintoma | Número |
|---|---|
| Oportunidade mediana | 90 |
| Oportunidade ≥ 90 | 129 de 198 (65%) |
| Oportunidade = 100 | 42 |
| Oportunidade = 0 | 10 |
| Churn mediana | 30 |
| Churn = 100 | 25 (13%) |
| Churn = 0 | 49 |

Distribuição de oportunidade concentrada em dois valores exatos: 84 reuniões em 90
e 42 em 100.

### O defeito é a fórmula, não o modelo

Recalculando a soma reta a partir dos códigos já gravados nos chunks, a
distribuição gravada se reproduz (mesmos picos em 90 e 100). A IA escolhe os
códigos; a saturação nasce de como eles são somados em
`scoring_service.calculate_opportunity_score`.

### Frequência dos códigos declarados (926 chunks)

| Código | Chunks | Pontos hoje |
|---|---|---|
| INTERESSE_NOVO_MODULO | 708 (76%) | 20 |
| PEDIDO_EXPANSAO | 480 (52%) | 40 |
| MENCAO_BUDGET | 281 (30%) | 30 |
| PRAZO_DEFINIDO | 54 (6%) | 25 |
| ELOGIO_CLIENTE | 22 (2%) | 15 |
| INSATISFACAO_EXPLICITA | 228 (25%) | 30 |
| MENCAO_CONCORRENTE | 103 (11%) | 25 |
| RECLAMACAO_PRODUTO | 31 (3%) | 15 |
| AMEACA_CANCELAMENTO | 30 (3%) | 50 |
| INATIVIDADE_PROLONGADA | 3 (0,3%) | 10 |

Os três códigos mais comuns de oportunidade somam 20 + 40 + 30 = 90, e é por isso
que 84 reuniões pousam exatamente nesse valor. Com `PRAZO_DEFINIDO` dá 115, capado
em 100.

### O score mede o tamanho da reunião

Mediana de oportunidade por número de chunks:

| Chunks | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 10+ |
|---|---|---|---|---|---|---|---|---|---|
| Oportunidade mediana | 20 | 65 | 90 | 90 | 90 | 90 | 90 | 90 | 90–100 |

Os códigos de todos os chunks da reunião são unidos em `_motives_for`
(`analysis_service.py`), então reunião longa acumula códigos por exposição: alguém
dizendo "quero conhecer a ferramenta" em qualquer trecho já garante
`INTERESSE_NOVO_MODULO`.

**Dois defeitos somados:** união dos códigos entre chunks, e soma reta de pontos
desenhados para um sinal forte isolado.

---

## 2. O que já foi simulado

Simulação a partir dos motivos gravados, sem LLM e sem reprocessar (segundos).

| Fórmula | Oportunidade | Churn |
|---|---|---|
| Soma reta (hoje) | mediana 90, 66% ≥ 90, 45 em 100 | mediana 30, 8% ≥ 90 |
| Retorno decrescente (1, ½, ¼, ⅛) | mediana 60, nenhum ≥ 90 | mediana 30, nenhum ≥ 90 |
| Código só conta se declarado em ≥ 25% dos chunks | mediana 90, 100s caem de 42 para 17 | zeros sobem de 49 para 84 |
| As duas juntas | mediana 60, nenhum ≥ 90 | zeros 84 |

Nenhuma resolve sozinha:

- **Decrescente pura** mata a saturação mas comprime tudo entre 40 e 64, e aí o
  número perde poder de separar reuniões.
- **Corte por frequência puro** derruba os 100 mas cala sinal real: os 35 zeros
  novos de churn precisam ser conferidos um por um antes de aceitar esse corte.

---

## 3. Passos

### Passo 1 — Conjunto rotulado — **descartado em 2026-10-09**

A ideia era 25 reuniões rotuladas por alguém do comercial (churn e oportunidade
em alto/médio/nenhum) para medir acerto em vez de só olhar a distribuição. O CSV
chegou a ser gerado e foi descartado: o custo é uma hora de trabalho manual
repetitivo, e quem decide se o ranking faz sentido já é a mesma pessoa que olharia
o dashboard.

O que ficou no lugar: comparar uma reunião reanalisada com a régua nova contra o
número que ela tem hoje, no próprio dashboard. Se o ranking passar a fazer
sentido para o comercial, a régua serve. O gabarito volta à mesa se alguém
discordar do ranking e for preciso provar quem está certo.

### Passo 2 — Simulador como ferramenta fixa

O script da simulação vira `ia/scripts/score_sim.py`: lê os motivos já gravados,
aplica N réguas e imprime a distribuição de cada uma. Sem LLM, sem reprocessar. É
o que permite iterar peso sem gastar GPU.

### Passo 3 — Pontos iniciais recalibrados pela frequência

Código comum vale menos; código raro vale mais. Estes são **valores iniciais** da
tabela do passo 4, a validar no simulador — não números cravados no código.

| Oportunidade | Hoje | Proposto | Motivo |
|---|---|---|---|
| PEDIDO_EXPANSAO | 40 | 30 | aparece em 52% dos chunks |
| MENCAO_BUDGET | 30 | 20 | 30% |
| PRAZO_DEFINIDO | 25 | 25 | 6%, discrimina bem |
| INTERESSE_NOVO_MODULO | 20 | 5 | 76%, quase constante |
| ELOGIO_CLIENTE | 15 | 10 | 2% |

| Churn | Hoje | Proposto |
|---|---|---|
| AMEACA_CANCELAMENTO | 50 | 50 |
| INSATISFACAO_EXPLICITA | 30 | 20 |
| MENCAO_CONCORRENTE | 25 | 20 |
| RECLAMACAO_PRODUTO | 15 | 15 |
| INATIVIDADE_PROLONGADA | 10 | 10 |

Com isso o trio comum de oportunidade vira 55 em vez de 90, e o teto passa a
exigir sinal raro.

### Passo 4 — Pesos e nomes no banco, editáveis

Hoje a tabela de pontos é constante no código (`CHURN_POINTS` e
`OPPORTUNITY_POINTS` em `ia/src/app/services/scoring_service.py`), e mudar um peso
exige deploy.

**Tabela nova no schema `ai`**, uma linha por motivo:

- código (chave, imutável), lado (churn ou oportunidade);
- nome curto e descrição, para a interface;
- pontos, ativo;
- `updated_at` e quem alterou.

Regras:

- A migração popula com os valores de hoje: nada muda no dia da subida.
- O serviço lê a tabela com cache em memória e cai nas constantes se a tabela
  estiver vazia. O cache invalida na escrita.
- **Score gravado é histórico.** Mudar peso não reescreve análise antiga.
- **Versão da régua:** um contador sobe a cada salvamento e é gravado junto do
  score, para que dois números do dashboard continuem comparáveis.
- **Limites:** 0 a 100 por motivo, edição só para diretor comercial, e aviso
  quando a soma dos dois maiores passa de 100 — é o que gera saturação.
- **Simular antes de salvar:** a tela mostra a distribuição resultante sobre as
  análises já gravadas, reusando o simulador do passo 2.

**API**

| Rota | Uso |
|---|---|
| `GET /api/dashboard/scoring` | motivos, pesos, nomes e versão da régua |
| `PUT /api/dashboard/scoring` | salva e devolve a versão nova |

A IA lê a tabela direto; o backend expõe a edição.

**Tela** (seção em Configurações): duas listas, Risco de churn e Oportunidade. Cada
motivo com nome, descrição, campo de 0 a 100 e a **frequência real** ("aparece em
76% das reuniões analisadas") — é ela que impede calibrar no escuro. Botões:
Simular, Salvar, Restaurar padrão.

### Passo 5 — Fórmula: peso por evidência e retorno decrescente

- **Peso por evidência, não por presença.** O código entra cheio quando aparece em
  pelo menos 25% dos chunks ou tem trecho literal confirmado pelas regras de
  `motive_rules.py`; aparição única em reunião longa entra com peso reduzido.
  Resolve a correlação com o tamanho da reunião sem zerar sinal isolado forte, que
  foi o problema do corte seco.
- **Retorno decrescente a partir do terceiro código.** Primeiro e segundo cheios,
  terceiro pela metade, quarto a um quarto. Mantém espalhamento (o problema da
  decrescente pura) e tira o estouro automático.

### Passo 6 — Nomes para gente, não para banco

Os códigos continuam como são no banco, no schema da IA e na API: são chave, e
renomear chave quebra análise antiga. Muda o que aparece na tela. Já existe
`MOTIVE_LABELS` em `analysis_service.py`, mas ele é justificativa em frase; falta o
nome curto para card, filtro e tela de pesos.

| Código | Nome curto | Descrição |
|---|---|---|
| AMEACA_CANCELAMENTO | Ameaça de saída | Cliente falou em cancelar ou não renovar |
| INSATISFACAO_EXPLICITA | Insatisfação declarada | Cliente disse que está insatisfeito |
| MENCAO_CONCORRENTE | Concorrente na mesa | Cliente citou outro fornecedor ou alternativa |
| RECLAMACAO_PRODUTO | Falha no produto | Erro, lentidão ou limitação relatada |
| INATIVIDADE_PROLONGADA | Cliente parado | Sem uso ou sem retorno há tempo |
| PEDIDO_EXPANSAO | Pedido de ampliação | Cliente quer mais escopo, licenças ou unidades |
| MENCAO_BUDGET | Verba citada | Valor, orçamento ou investimento mencionado |
| PRAZO_DEFINIDO | Prazo combinado | Data concreta acordada na reunião |
| INTERESSE_NOVO_MODULO | Interesse em novidade | Cliente perguntou por produto que ainda não tem |
| ELOGIO_CLIENTE | Elogio do cliente | Cliente elogiou produto ou atendimento |

- **Um lugar só:** nome curto e descrição moram na tabela do passo 4, e a API
  entrega os dois junto do peso. Sem dicionário duplicado no frontend.
- **Nome é editável, código não.**
- **Dois comprimentos:** nome curto para chip e filtro, descrição para tooltip e
  tela de pesos.
- Vale também para "Risco de churn" no card: "Risco de perder o cliente" diz o
  mesmo sem jargão.

### Passo 7 — Travas e testes

- Piso de enumeração por lado: 5 para churn, 4 para oportunidade. Com 4 códigos a
  soma já passava de 100, então a trava nunca disparou desse lado.
- Teto 100 só alcançável com `AMEACA_CANCELAMENTO` mais um código raro.
- Teste de que o score não correlaciona com número de chunks.

### Passo 8 — Recálculo das análises antigas (opcional)

As 198 análises podem ser recalculadas a partir dos `chunk_summary` já gravados,
sem LLM. O time pediu para manter as antigas como feedback, então isso só roda sob
pedido: script idempotente, uma transação, registrando a versão da régua usada.

---

## 4. Fora deste plano, a decidir

A outra metade do erro é a IA declarar `INTERESSE_NOVO_MODULO` em 76% dos chunks.
Isso é prompt, e a orientação atual é não mexer no raciocínio dela. Apertar a
definição do código ("só quando o cliente pergunta por produto que ainda não tem")
provavelmente derruba mais do que qualquer ajuste de peso — mas é mudança de
prompt, com medição obrigatória nos dois perfis (ver `CLAUDE.md`, "Medir antes de
afirmar").

---

## 5. Critério de pronto

1. Oportunidade: no máximo 15% das reuniões acima de 90, mediana entre 40 e 60,
   zeros preservados.
2. Churn 100 só onde o rótulo humano diz churn alto.
3. O comercial olha o ranking do dashboard e concorda com a ordem.
4. Score sem correlação com o número de chunks.
5. Diretor comercial consegue mudar um peso, simular e salvar sem deploy, e as
   análises antigas continuam com o número com que foram medidas.

---

## 6. O que foi implementado em 2026-10-09

Nenhuma análise foi reprocessada: as 198 que existem guardam os códigos e os
scores com que foram medidas. Tudo abaixo vale para as próximas análises.

| Passo | Estado | Onde |
|---|---|---|
| 1 — conjunto rotulado | **descartado**, ver passo 1 | — |
| 2 — simulador | feito, sem a parte de rótulos | `ia/scripts/score_sim.py` |
| 3 — pontos recalibrados | feito como preset do simulador, **não aplicado** | `PLAN_POINTS` em `score_sim.py` |
| 4 — pesos e nomes no banco | feito | migração `0010`, `ai.scoring_weights`, `scoring_config_service.py`, `/scoring` na IA, `/api/dashboard/scoring` no backend, `frontend/src/pages/Settings.tsx` |
| 5 — fórmula | feito | `scoring_service._score` |
| 6 — nomes de tela | feito | colunas `name`/`description` da tabela, servidas pela API |
| 7 — travas e testes | feito, menos o piso de 4 | `ia/tests/test_scoring_service.py`, `ia/tests/test_scoring_config.py`, `backend/tests/test_scoring_api.py` |
| 8 — recálculo | script pronto, **não executado** | `ia/scripts/rescore.py` (sem `--apply` só compara) |

### O efeito medido da fórmula, sem mexer em peso nenhum

Simulado sobre as 201 análises gravadas, sem LLM:

| Régua | Oportunidade | Churn |
|---|---|---|
| soma reta (antes) | mediana 90, 129 ≥ 90, 42 em 100 | mediana 30, 25 em 100 |
| nova fórmula, pesos de hoje | mediana 79, nenhuma ≥ 90, 10 zeros | mediana 28, 5 ≥ 90, 65 zeros |
| nova fórmula, pesos do passo 3 | mediana 53, nenhuma ≥ 90, 10 zeros | mediana 20, nenhuma ≥ 90, 65 zeros |

A fórmula sozinha tira a saturação; os pesos do passo 3 é que trazem a mediana
para a faixa de 40 a 60 do critério 1. Como os pesos agora moram no banco, aplicar
o passo 3 é uma edição na tela, sem deploy — e o simulador mostra o resultado
antes de salvar.

### Duas decisões diferentes do que o plano previa

- **O piso de enumeração da oportunidade fica em 5, não em 4.** O motivo do 4 era
  que quatro códigos já estouravam 100; com o retorno decrescente eles dão 88, e o
  piso de 4 passaria a descartar a leitura de quatro códigos que já foi medida como
  legítima. Fica como está até alguém apontar um caso real em que erra.
- **A migração popula com os pesos de hoje**, não com os do passo 3. Assim a
  subida não muda peso nenhum, e a recalibração é uma decisão registrada na versão
  da régua, não um efeito colateral de deploy.

### O aperto do prompt foi medido e descartado

`INTERESSE_NOVO_MODULO` (seção 4) continua com a definição antiga. Três catálogos
sobre os mesmos 20 chunks deram 11, 10 e 9 declarações de 20 — e o próprio prompt
de produção, rodando de novo sobre chunks que já tinham o código, varia cerca de
um terço entre rodadas. A diferença entre os textos é menor que o ruído do modelo.
Detalhes e números em `docs/prompts.md`, "Quarta rodada".

Consequência para este plano: a seção 4 deixa de ser "a outra metade do erro". O
que resta do lado da IA é o peso de 20 para 5 (passo 3), que é determinístico, e o
peso por evidência (passo 5), que já faz uma menção única valer metade.
