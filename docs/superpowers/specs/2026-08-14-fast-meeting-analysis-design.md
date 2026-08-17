# Design — análise completa de reuniões em 3–5 minutos

## Objetivo

Reduzir o tempo de análise de uma transcrição de aproximadamente 40 mil tokens
para, idealmente, até cinco minutos na VPS de referência com 2 vCPU e 8 GB de
RAM. A meta cobre resumos parciais e consolidação final. Embeddings não fazem
parte do caminho crítico.

A meta é um objetivo de desempenho sujeito a benchmark, não uma garantia prévia.
Se o hardware não a alcançar, o sistema deve registrar o menor tempo obtido e
continuar entregando uma análise completa e retomável.

## Restrições de qualidade

A otimização pode tornar o texto mais sintético, mas não pode remover:

- decisões e compromissos explícitos;
- responsáveis, valores, quantidades e prazos;
- problemas, dúvidas e negações;
- evidências relevantes e ações acordadas.

O sistema não deve inventar ações ou fatos. A variante vencedora precisa manter
os campos obrigatórios do JSON atual.

## Arquitetura proposta

O pipeline terá quatro etapas no caminho crítico:

1. limpeza determinística e divisão eficiente da transcrição;
2. resumos parciais curtos, sem modo de raciocínio estendido;
3. consolidação final com o modelo de maior qualidade;
4. persistência do dashboard completo.

Os embeddings continuam depois do dashboard e não entram na medição de três a
cinco minutos.

### Retenção relevante agressiva

Como o benchmark demonstrou que a leitura integral domina o tempo em CPU, o
modo rápido seleciona deterministicamente uma fração configurável das falas
antes dos chunks. Serão comparadas retenções de 15%, 25% e 35%. A pontuação
prioriza números, moeda, datas, prazos, perguntas, negações, decisões, ações,
problemas e evidências; os trechos escolhidos voltam à ordem cronológica.

Depois da consolidação, o serviço identifica campos obrigatórios ausentes ou
vazios. Uma única chamada curta recebe somente os resumos compactos e o JSON
parcial, com schema contendo apenas os campos faltantes. O resultado é mesclado
sem substituir campos já preenchidos.

### Limpeza e divisão

A limpeza deve operar por falas, antes da divisão em chunks:

- compactar marcadores como `[LOCUTOR 117]` para `[L117]`;
- unir fragmentos consecutivos do mesmo locutor;
- remover falas inteiras compostas apenas por cumprimento, confirmação ou teste
  técnico;
- remover repetições exatas;
- preservar números, valores, prazos, perguntas, negações e falas com conteúdo;
- dividir preferencialmente em limites de fala;
- reduzir o overlap ao mínimo necessário, inclusive zero quando o limite de fala
  preservar o contexto.

O sistema registra tokens antes e depois, percentual de redução e total de
chunks.

### Geração parcial

A configuração candidata principal usa `qwen2.5:1.5b` para chunks, com `think`
desativado e resposta limitada a aproximadamente 300–400 tokens. O prompt exige
frases curtas e listas sem repetição.

O modelo de chunks será configurável separadamente do modelo de consolidação.
Isso permite comparar o Qwen 1.5B com o Qwen 3B sem alterar código.

Cada resultado válido continua sendo salvo imediatamente. Uma falha nunca deve
recalcular chunks já concluídos.

### Consolidação

A consolidação usa `qwen2.5:3b`, também sem raciocínio estendido inicialmente,
com saída suficiente para preencher o dashboard. Ela recebe resumos parciais
compactos, remove duplicações e mantém referências importantes.

### Concorrência adaptada ao hardware

Concorrência 1 é o padrão seguro. Concorrência 2 será habilitada somente se o
benchmark demonstrar redução do tempo total sem exceder a memória disponível ou
degradar a qualidade.

O worker poderá processar até dois chunks independentes da mesma análise, mas a
ordem de persistência e consolidação será pelo índice original. A concorrência
entre reuniões continua limitada para evitar disputa pelo Ollama.

O Ollama será testado com paralelismo correspondente e modelo mantido carregado.
Não será usado paralelismo maior que 2 na VPS de referência.

## Recuperação de respostas inválidas

A resposta textual bruta do Ollama deve ser registrada de forma limitada e sem
incluir toda a transcrição. Se o JSON não puder ser decodificado:

1. tentar extração determinística de um objeto JSON válido;
2. fazer no máximo uma tentativa curta de reparo pelo modelo;
3. validar o objeto e os campos obrigatórios;
4. persistir o chunk reparado ou marcar somente esse chunk como pendente.

Retries não devem apagar checkpoints nem repetir chunks concluídos.

## Configuração

As seguintes decisões serão configuráveis por ambiente:

- modelo de chunks e modelo de consolidação;
- limite de tokens por chunk e overlap;
- `think` e `num_predict` de cada etapa;
- concorrência de chunks, limitada a 1 ou 2;
- ativação da limpeza aprimorada;
- tentativa de reparo de JSON.

Os valores padrão serão escolhidos pelo benchmark, não por estimativa.

## Benchmark

A mesma transcrição manual de aproximadamente 40 mil tokens será usada em todas
as variantes:

1. Qwen 3B atual, como baseline;
2. Qwen 3B com limpeza, prompts e limites otimizados;
3. Qwen 1.5B nos chunks e Qwen 3B na consolidação;
4. melhor variante anterior com concorrência 2.

Cada execução registra:

- tokens e chunks antes e depois da limpeza;
- tempo de preparação, cada chunk e consolidação;
- tempo até o dashboard completo;
- pico de RAM e utilização de CPU;
- falhas, retries e reparos de JSON;
- presença dos fatos críticos definidos nas restrições de qualidade.

Modelos devem estar previamente carregados para separar tempo de download e
primeiro carregamento do tempo normal de análise. Também será registrada uma
execução fria para informar o comportamento após reinício.

## Critérios de aceite

- A análise final é persistida com todos os campos obrigatórios.
- Chunks concluídos permanecem retomáveis após qualquer falha.
- Nenhum fato crítico da amostra de referência desaparece em relação ao baseline
  validado.
- O processo permanece dentro da RAM disponível, sem swap excessivo ou término
  por falta de memória.
- A melhor configuração busca tempo quente de até cinco minutos para a amostra
  de 40 mil tokens.
- Se nenhuma configuração atingir cinco minutos, o relatório apresenta o menor
  tempo medido e identifica o gargalo antes de recomendar GPU ou API externa.

## Fora do escopo

- troca definitiva para um provedor externo antes do benchmark local;
- paralelismo maior que 2 na VPS de referência;
- tradução da transcrição para inglês;
- compressão por um segundo Transformer;
- mudanças no frontend além de consumir o dashboard já existente.
