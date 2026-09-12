# Importação de reuniões CSV e JSON

Data: 2026-09-04. Implementação de API para a POC e novos arquivos, com
persistência e bloqueio de duplicatas. Substitui a proposta de ler JSON fixo
diretamente no backend. A integração visual do React, Alembic e a consolidação
completa dos `.env` continuam como frentes separadas.

## Fluxo implementado

```mermaid
flowchart TD
    A[Upload CSV ou JSON com JWT] --> B[Limite de tamanho e validação]
    B --> C{Arquivo ou conteúdo já importado?}
    C -->|Sim| X[409 sem chamar IA]
    C -->|Não| D{IDs existentes com texto diferente?}
    D -->|Sim| Y[Nova versão; versão anterior intacta]
    Y --> E
    D -->|Não| E[Persistir reuniões novas no PostgreSQL]
    E --> F[201 com import_id e contagens]
    F --> G[GET lista e detalhe da reunião]
    G --> H[POST analysis por reunião]
    H --> I[Resolver transcrição salva e chave de idempotência]
    I --> J[IA: reservar chave e criar análise + chunks]
    J --> K[Fila existente de análise]
    K --> L[Resumo pronto]
    L --> M[Embeddings no pgvector]
    M --> N[DONE: RAG disponível]
```

Importar não dispara análise nenhuma. O envio à IA é explícito por reunião,
para controlar a carga; `make reunioes` faz esse envio em lote, uma por vez. A importação limitada é síncrona, sem fila
extra: retorna 201 após a transação de persistência. O trabalho pesado continua
na fila existente da IA e sua rota retorna 202.

## Formatos

CSV UTF-8, com ou sem BOM, delimitado por vírgula ou ponto e vírgula.
Campos obrigatórios: `ID_MEETING` e `ANON_TRANSCRICAO`. As demais colunas são
metadados; `TITLE` é opcional e o título padrão é `Reunião {ID_MEETING}`.
Não inferimos cliente ou status de análise a partir de colunas ambíguas.
`STATUS_MEETING` e `NOTA_NPS` são dados da fonte, não resultado da IA.

```csv
ID_MEETING,ANON_TRANSCRICAO,UF,NOTA_NPS
100,"locutor_1 Precisamos de 20 licenças.",SP,9
```

JSON aceita a lista equivalente, ou `{"meetings": [...]}`. Também aceita
`meeting_id`, `transcription` e `title` como aliases dos campos de entrada:

```json
[
  {
    "meeting_id": "100",
    "transcription": "locutor_1 Precisamos de 20 licenças.",
    "UF": "SP",
    "NOTA_NPS": 9
  }
]
```

Limites: 5 MiB por arquivo, 1.000 reuniões por importação e IDs de até 512 bytes
UTF-8. O corpo HTTP é limitado antes de processar multipart, com 64 KiB de
margem para o envelope. CSV com colunas inconsistentes, IDs duplicados dentro
do arquivo, JSON malformado, campos ambíguos, texto vazio, NUL e metadados
aninhados são rejeitados antes de persistir.

A transcrição recebida é preservada. Metadados são strings normalizadas; o
parser não converte datas, durações ou NPS em métricas de dashboard. JSON com
somente `transcriptSnippet`, como os mocks antigos do frontend, não é uma
fonte válida de transcrição integral.

## Regras de duplicidade

| Entrada | Resultado |
|---|---|
| Mesmo arquivo, inclusive renomeado | 409 `DUPLICATE_IMPORT` |
| CSV convertido em JSON ou linhas reordenadas | 409 se os registros equivalem aos já importados |
| Arquivo diferente contendo apenas IDs/textos existentes | 409 `DUPLICATE_IMPORT` |
| Mistura de reuniões existentes e novas | Importa novas; reporta `skipped_count` |
| ID existente com transcrição diferente | Cria nova versão da reunião; conta em `versioned_count` |
| ID existente, mesmo texto, só metadados alterados | Ignora a reunião; mantém dados anteriores |
| Texto voltando a uma versão anterior do mesmo ID | Ignora; não cria versão nova |
| Textos iguais com IDs de reuniões diferentes | São reuniões distintas, com contextos RAG separados |
| Clique repetido/simultâneo para analisar | Reutiliza `analysis_id`; uma única criação |
| Timeout no envio para IA | Nova tentativa usa a mesma chave; não cria outra análise |

A deduplicação é por usuário autenticado. Não se compartilham transcrições,
análises ou existência de arquivos entre usuários. Uma organização com vários
usuários deverá definir o escopo de tenant antes de compartilhar importações.

Hash do arquivo usa os bytes; hash do conteúdo usa campos ordenados e
normalização conservadora de Unicode/espaços. Maiúsculas, pontuação e IDs não
são descartados. Não usamos embeddings para decidir se dois arquivos são iguais.
Bloqueios de linha por usuário e constraints únicas no PostgreSQL protegem
upload simultâneo em processos diferentes.

## Endpoints e execução

Suba a stack pelo Docker Compose, da raiz do repositório — é o único modo
suportado:

```sh
docker compose up -d --build
```

A configuração vem do `.env` da raiz; o Compose injeta os mesmos valores como
variáveis de ambiente, que têm precedência dentro do container. Não rode o
backend com `uvicorn` no host: `IA_SERVICE_URL` aponta para `ia-service`, um nome
que só resolve dentro da rede do Compose.
Use `http://localhost:8080/docs`: registre/logue o usuário, copie `access_token`
para o botão Authorize e envie o arquivo em `POST /api/imports`.

| Rota | Uso |
|---|---|
| `POST /register`, `POST /login` | Autenticação existente |
| `POST /api/imports` | Multipart com campo `file`; retorna contagens e `import_id` |
| `GET /api/imports/{import_id}` | Consultar comprovante da importação |
| `GET /api/meetings?offset=0&limit=50` | Lista paginada sem transcrição integral; máximo 100. Só a versão vigente, salvo `include_versions=true` |
| `GET /api/meetings/{id}/versions` | Histórico completo do `external_id`, da versão 1 em diante |
| `GET /api/meetings/{id}` | Metadados e transcrição recebida |
| `POST /api/meetings/{id}/analysis` | Inicia/reutiliza análise usando dados salvos |
| `GET /api/meetings/{id}/analysis` | Progresso, resumo e prontidão RAG |

Os IDs internos expostos pela API são UUID; o ID externo do CSV permanece em
`external_id`. O frontend nunca precisa baixar e reenviar a transcrição para
iniciar a análise. A adaptação `locutor_1` → `[LOCUTOR 1]:` ocorre apenas no
envio à IA, para utilizar seu tratamento existente.

O backend preserva status e campos de progresso da IA e acrescenta
`summary_ready` e `rag_ready`. Resumo final disponível durante `EMBEDDING` ou
`DASHBOARD_READY_WITH_EMBEDDING_ERROR` não habilita RAG. `DONE` habilita RAG;
as rotas existentes de busca/chat também verificam ausência de embeddings.
Busca continua isolada por `analysis_id`, com distância cosseno, limiar,
evidências/citações e fallback sem suporte. Não alteramos modelo, dimensão de
vetor, limites de chunks ou heurísticas de recuperação.

## Carga do CSV inteiro

`transcricoes_TOTVS.csv` tem 38 MiB e 1.044 reuniões, acima dos limites de um
upload. `make reunioes` roda `backend/scripts/load_dataset.py` no container do
backend:

1. divide o CSV em partes abaixo dos dois limites e valida cada uma com o parser do
   backend antes de enviar;
2. importa as partes com a conta de `KOLIA_EMAIL`/`KOLIA_PASSWORD` do `.env`;
3. informa quantas reuniões vão ser analisadas, dispara uma por vez e espera cada
   uma chegar em `DONE`, mostrando o tempo médio e quanto falta.

A divisão é sempre a mesma, então rodar de novo reenvia partes idênticas, que voltam
como `DUPLICATE_IMPORT`, e as reuniões concluídas são puladas. Se reuniões de uma
parte já importada foram excluídas depois, o registro do import continua lá e a
parte idêntica é recusada. Nesse caso o script confere quais reuniões da parte
faltam na conta e reenvia só essas, num arquivo com bytes diferentes. `make reunioes-plano`
só divide e valida; `make reunioes LIMIT=5` é um ensaio curto.

Uma falha no envio conta e o lote segue; cinco seguidas param tudo, porque aí o
problema é o serviço. Uma análise sem progresso por 10 minutos é marcada como
travada. Só entram reuniões **deste CSV** e **sem análise**. Reuniões de outros
imports da mesma conta ficam de fora: em 2026-09-12 a conta tinha também 454 de
um `ds.csv` antigo, e o primeiro ensaio analisou cinco delas antes desse filtro. A
que terminou em erro ou travou já tem análise ligada e não é reenviada;
reprocessá-la é manual.

Medido em 2026-09-12: as 9 partes importaram 1.043 reuniões novas e 1 versão.
Reuniões de ~5 a 7 mil palavras levaram de 2 a 3 minutos cada numa GTX 1070 Ti;
as 1.044 somam uns 2 a 3 dias.

## Reprocessamento e versões

Quando um `external_id` já importado chega com transcrição diferente, o registro
anterior não é alterado: gravamos uma **nova versão**, com novo UUID interno e
`version` incrementado. A versão anterior mantém sua transcrição, sua análise,
seus chunks e seus embeddings, então citações já exibidas continuam resolvendo.

A chave de idempotência enviada à IA deriva do UUID interno mais o hash da
transcrição, e cada versão é uma linha nova. A IA, portanto, não precisou mudar:
a nova versão recebe análise e chunks próprios, e a busca continua isolada por
`analysis_id`. Analisar é sempre explícito por versão; importar não dispara nada.

Reenviar um conteúdo que já existe em *qualquer* versão daquele ID é ignorado, e
não cria versão nova. É isso que impede um ciclo de edição A → B → A de crescer
uma versão a cada upload. Um lote sem nenhuma reunião nova nem revisada continua
retornando 409 `DUPLICATE_IMPORT`.

`GET /api/meetings` devolve apenas a versão vigente de cada `external_id`; use
`include_versions=true` para ver as superadas, ou `/versions` para o histórico de
uma reunião. Não há remoção nem sobrescrita de versões antigas: a limpeza de
versões antigas, se desejada, é uma política à parte ainda não definida.

## Busca e recuperação

Cada bloco de ~2000 tokens é fatiado em passagens de ~400 (`ai.chunk_passages`),
embeddadas individualmente. O bloco existe para resumir com poucas chamadas ao
LLM; a passagem existe para buscar. Medido: um vetor sobre o bloco inteiro não
trazia nenhuma das sete passagens que citam `R$` ao ser perguntado por valores.

A busca roda por dois caminhos e funde por posição. O vetorial casa por assunto;
o textual (`tsvector` em português, índice GIN) casa por palavra. Os termos da
pergunta que aparecem em mais de 35% das passagens daquela análise são
descartados — medido contra o próprio corpus, não contra uma lista escrita à mão,
porque uma palavra genérica numa reunião pode ser o assunto central de outra.

Análises indexadas antes das passagens continuam respondendo pelo vetor do bloco;
o caminho antigo é o fallback. Reindexar não chama o LLM: são só os embeddings.

## Persistência e retomada

`core.meeting_imports` armazena hashes/contagens. `core.meetings` guarda origem,
transcrição, metadados e vínculo à análise. `ai.analysis_submissions` guarda a
chave de idempotência e o hash do payload. Todo o schema vem do Alembic, um por
serviço (`backend/migrations`, `ia/migrations`). O container roda `alembic upgrade
head` antes de subir, e o backend recusa iniciar com o banco fora da `head`. O
`001_meeting_versions.sql` e o bootstrap por `create_all` de versões anteriores
deste documento não existem mais.

A IA reserva a chave antes de preparar os dados. Para requisições com chave,
análise, chunks e vínculo à reserva são salvos juntos. Reenvios retornam o
vínculo persistido e não reenfileiram. Se o processo parar após o commit e antes
de enfileirar, a recuperação existente do worker no startup retoma a análise.
Se a preparação falhar antes do commit, a reserva sem vínculo retorna 409 para
revisão: não é removida ou expirada automaticamente.

Na prática, o backend responde `409 ANALYSIS_NOT_READY` para uma reunião que não
tem análise. Em 2026-09-12 a reunião 1000249 estava assim por uma reserva de
2026-09-10. Conferido que a chave era dela e que não havia análise ligada, a linha
foi apagada de `ai.analysis_submissions`, e o envio seguinte foi aceito.

Clientes legados da IA sem `Idempotency-Key` mantêm seu comportamento. Em
produção, o ingresso público deve acessar o backend; a IA deve ficar na rede
interna. O worker existente ainda deve operar em uma única instância da IA:
este trabalho não introduz coordenação distribuída de workers.

## Validação reproduzível

Execute as suítes separadamente por serviço (os imports Python usam caminhos
próprios). Banco de teste deve ser descartável: o fixture do backend limpa as
tabelas desse banco entre casos e exige nome iniciado em `kolia_import_test`.

```sh
docker compose run --rm --no-deps \
  -e TEST_DATABASE_URL=postgresql+psycopg2://usuario:senha@host:5432/kolia_import_test \
  backend sh -c "pip install -q pytest && python -m pytest -q tests"
docker compose build ia-service
docker run --rm --network host \
  -e DATABASE_URL=postgresql+psycopg2://kolia:kolia@localhost:5433/kolia \
  -e SECRET_KEY=<32+ caracteres> \
  dashboard-kolia-ia-service python -m pytest -q tests
```

O teste PostgreSQL da IA é opcional com `TEST_DATABASE_URL`, usando um schema
aleatório exclusivo de teste. O CSV real é somente leitura e seus testes são
ignorados se o arquivo local não estiver presente. Testes da API simulam HTTP
da IA e as suítes de IA simulam o Ollama. Nenhuma dessas suítes executa as análises
do dataset ou valida desempenho/qualidade de inferência em hardware real; para isso
existe `make reunioes LIMIT=5`.
