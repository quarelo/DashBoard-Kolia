# Docker Compose simples do Kolia — Plano de implementação

> **Para execução agentic:** usar `superpowers:executing-plans` e executar as tarefas em ordem. Não criar commits; o usuário fará isso depois.

**Objetivo:** Subir frontend, backend, IA, Postgres e Ollama em containers separados usando um único `docker compose up --build`.

**Arquitetura:** O `docker-compose.yml` da raiz será a única fonte de orquestração. Cada aplicação terá seu próprio Dockerfile, rede e stream de logs; Postgres e Ollama manterão volumes nomeados. Backend e IA permanecerão explicitamente incompletos.

**Stack:** Docker Compose, Node.js 22/Vite, Eclipse Temurin 17, Python 3.11/FastAPI, PostgreSQL 16 com pgvector e Ollama.

## Restrições globais

- Ambiente somente de desenvolvimento.
- Um container por serviço.
- Um único `docker-compose.yml` na raiz.
- Nenhum commit será criado pelo agente.
- Preservar `ia/src/app/main.py` e a remoção local de `ia/main.py`.

---

### Tarefa 1: Consolidar a orquestração

**Arquivos:**

- Modificar: `docker-compose.yml`
- Remover: `infra/docker-compose.yml`
- Remover: `ia/docker-compose.yml`

**Entrega:** Um único Compose com os serviços `frontend`, `backend`, `ia-service`, `postgres` e `ollama`, a rede `kolia-network` e volumes `postgres_data` e `ollama_data`.

- [ ] Validar o estado inicial com `docker compose config --quiet`.
- [ ] Manter contextos de build `./frontend`, `./backend` e `./ia`.
- [ ] Configurar URLs internas com os nomes dos serviços e publicar as portas `5173`, `8080`, `3000`, `11434` e `5433:5432`.
- [ ] Manter o healthcheck real do Postgres e fazer o backend depender de sua condição saudável sem exigir que IA ou Ollama estejam prontos.
- [ ] Remover os dois Compose duplicados.
- [ ] Executar `docker compose config --quiet`; resultado esperado: código de saída 0.
- [ ] Executar `docker compose config --services`; resultado esperado: exatamente os cinco serviços definidos.

### Tarefa 2: Corrigir as imagens dos serviços

**Arquivos:**

- Modificar: `frontend/Dockerfile`
- Modificar: `ia/Dockerfile`
- Verificar: `backend/Dockerfile`

**Entrega:** Cada imagem inicia o processo correto do seu serviço, com dependências reproduzíveis e sem copiar artefatos locais desnecessários.

- [ ] Trocar `npm install` por `npm ci` no frontend, usando o lockfile existente.
- [ ] Manter o Vite ouvindo em `0.0.0.0:5173`.
- [ ] Ajustar o comando da IA para `uvicorn src.app.main:app --host 0.0.0.0 --port 3000`.
- [ ] Manter o backend como placeholder explícito e ativo até existir código Spring Boot.
- [ ] Executar `docker compose build frontend backend ia-service`; resultado esperado: as três imagens construídas sem erro.

### Tarefa 3: Verificar inicialização e isolamento dos logs

**Arquivos:**

- Verificar: `docker-compose.yml`
- Verificar: `ia/src/app/main.py`

**Entrega:** O ambiente inicia com um comando e cada serviço possui logs consultáveis separadamente.

- [ ] Executar `docker compose up --build -d`; resultado esperado: comando concluído sem erro.
- [ ] Executar `docker compose ps -a`; resultado esperado: frontend, backend, IA, Postgres e Ollama não estão em estado `Exited`.
- [ ] Executar `curl --fail http://localhost:3000/health`; resultado esperado: JSON `{"status":"ok"}`.
- [ ] Executar `curl --fail http://localhost:5173`; resultado esperado: resposta HTTP bem-sucedida.
- [ ] Executar `docker compose logs --no-color frontend backend ia-service`; resultado esperado: streams identificados por serviço e sem erro de importação da IA.
- [ ] Executar `docker compose down`; resultado esperado: containers e rede removidos, volumes preservados.
- [ ] Executar `git diff --check`; resultado esperado: nenhuma falha de whitespace.
