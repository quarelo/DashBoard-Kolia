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

## Configuração

Existe **um** `.env`, na raiz, ao lado do `docker-compose.yml`. As configs dos dois
serviços o resolvem por caminho absoluto, então não importa de onde o uvicorn
roda. Dentro dos containers o arquivo não existe e o Compose injeta os mesmos
valores como variáveis de ambiente, que têm precedência.

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
