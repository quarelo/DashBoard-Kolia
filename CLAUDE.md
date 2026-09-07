# KOLIA — CLAUDE.md

Convenções do repositório. Veja também `backend/CLAUDE.md` para o serviço de
backend e `README.md` para a arquitetura.

## Commits

- **Não adicione `Co-Authored-By` nem linhas de sessão nas mensagens de commit.**
  O histórico registra o que mudou e por quê; autoria de ferramenta é ruído.
- Escreva o **porquê** na mensagem, com o número que sustenta a decisão quando
  houver um. "512 tokens" não se explica sozinho seis meses depois; "truncou em 6
  de 6 chamadas com 256 e em 1 de 6 com 512" se explica.
- Separe por assunto, para que cada commit possa ser revisado ou revertido só.

## Serviços

Dois serviços dividem um PostgreSQL e a fronteira é o schema: `core` é do
backend, `ai` é da IA, e nenhum escreve na tabela do outro. Cada um tem seu
Alembic e sua tabela de versão, no seu schema.

## Execução

**Tudo roda no Docker Compose, sempre.** Nada de `uvicorn` ou `npm run dev` no
host, nem para um teste rápido:

```bash
docker compose up -d --build
docker compose ps   # os cinco: postgres, ollama, ia-service, backend, frontend
```

`./backend` e `./frontend` são bind mounts com reload, então editar no host já
recarrega o container — subir à mão não adianta nada e quebra a rede. Os nomes
dos serviços são os hostnames: o backend só acha a IA em `http://ia-service:3000`
e a IA só acha o Ollama em `http://ollama:11434`, nomes que existem apenas dentro
de `kolia-network`.

Subir metade fora do Compose falha de um jeito que não parece rede. Com a IA
rodando no host em `127.0.0.1:3000` e o resto em container, o backend resolveu
`ia-service` para nada (`ConnectError: Name or service not known`) e o chat do
dashboard respondeu **503 `IA_UNAVAILABLE`** a toda mensagem, como se a IA
estivesse fora do ar. Publicar o processo do host em `0.0.0.0` também não
resolveria: falta o nome, não a porta.

Para depurar um serviço isolado, use o ambiente do próprio container
(`docker compose exec ia-service ...`) em vez de abrir um processo paralelo.

## Configuração

Existe **um** `.env`, na raiz, ao lado do `docker-compose.yml`. As configs dos dois
serviços o resolvem por caminho absoluto, então o diretório de trabalho não
importa. Dentro dos containers o arquivo não existe e o Compose injeta os mesmos
valores como variáveis de ambiente, que têm precedência — é assim que os
serviços recebem `postgres:5432` e `ollama:11434` no lugar do que o arquivo diz.

O arquivo usa os nomes que o Compose interpola (`JWT_SECRET`, `OLLAMA_MODEL`), e
as configs aceitam as duas grafias por `AliasChoices`.

## Frontend

**Não altere `frontend/` sem pedido explícito.** Ele ainda lê os JSON de exemplo
em `src/data/` e não consome as APIs.

## Testes

```bash
cd ia && .venv/bin/python -m pytest tests -q
TEST_DATABASE_URL=postgresql+psycopg2://... python -m pytest -q backend/tests
```

As suítes rodam separadas: os imports de cada serviço usam caminhos próprios.
Os testes do backend pulam sem `TEST_DATABASE_URL`, que precisa apontar para um
banco descartável cujo nome comece com `kolia_import_test`.

## Medir antes de afirmar

Este projeto roda um modelo pequeno num host apertado, e várias intuições
razoáveis se mostraram erradas na medição — subir `OLLAMA_NUM_PARALLEL`, forçar
threads SMT, trocar o governador de CPU, encurtar o prompt. Quando a mudança é de
desempenho ou de qualidade de saída, meça nos dois perfis que existem: as
reuniões curtas do CSV (~74 tokens) e a reunião longa de `ia/tests/test_analisar.py`
(~40 mil tokens). Uma otimização real num perfil costuma ser neutra ou nociva no
outro.
