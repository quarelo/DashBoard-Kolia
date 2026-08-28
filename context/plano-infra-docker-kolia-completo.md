# Plano Completo de Infraestrutura Docker — KOLIA

Este documento organiza a infraestrutura do projeto KOLIA usando Docker Compose, separando os serviços em containers independentes para facilitar desenvolvimento, logs, manutenção e evolução futura.

---

## 1. Objetivo

Montar uma arquitetura local de desenvolvimento com:

- Frontend Vite
- Backend Java Spring Boot
- Serviço de IA em Node.js
- Ollama rodando em container próprio
- Postgres com pgvector
- Scripts para instalar e remover modelos do Ollama
- Script principal para subir o ambiente e instalar o modelo caso ele não exista
- Logs separados por serviço
- Estrutura organizada com a pasta `infra/`

---

## 2. Estrutura de pastas recomendada

```txt
projeto/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│
├── back/
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/
│
├── IA/
│   ├── Dockerfile
│   ├── package.json
│   ├── server.js
│   └── logs/
│
└── infra/
    ├── docker-compose.yml
    ├── .env
    ├── postgres/
    │   └── init.sql
    └── scripts/
        ├── start-dev.js
        ├── install-model.js
        └── delete-model.js
```

---

## 3. Arquitetura geral

```txt
[ Frontend Vite ]
        ↓
[ Backend Spring Boot ]
        ↓
[ IA Service Node.js ]
        ↓
[ Ollama ]

[ Backend Spring Boot ] → [ Postgres + pgvector ]
```

Regra principal:

```txt
Frontend nunca chama IA direto.
Frontend chama Backend.
Backend chama IA Service.
IA Service chama Ollama.
Backend salva no Postgres.
```

---

## 4. Responsabilidade de cada serviço

### 4.1 Frontend

Responsável por:

- Login
- Tela de upload de transcrição
- Listagem de reuniões
- Visualização de relatório
- Perguntas para IA
- Consumo da API do backend

URL local:

```txt
http://localhost:5173
```

---

### 4.2 Backend

Responsável por:

- Autenticação
- Usuários
- Permissões
- Reuniões
- Status de processamento
- Comunicação com IA Service
- Persistência no Postgres

URL local:

```txt
http://localhost:8080
```

---

### 4.3 IA Service

Responsável por:

- Receber transcrição
- Dividir em chunks
- Limpar ruídos
- Gerar análise estruturada
- Consolidar relatório final
- Chamar Ollama
- Gerar logs do processamento

URL local:

```txt
http://localhost:3000
```

---

### 4.4 Ollama

Responsável por:

- Rodar o modelo local
- Receber chamadas da IA Service
- Gerenciar modelos baixados

URL local:

```txt
http://localhost:11434
```

---

### 4.5 Postgres + pgvector

Responsável por:

- Usuários
- Reuniões
- Relatórios
- Chunks
- Embeddings vetoriais
- Dados relacionais do sistema

URL local:

```txt
localhost:5432
```

---

## 5. Arquivo `.env`

Arquivo:

```txt
infra/.env
```

Conteúdo recomendado:

```env
POSTGRES_DB=kolia
POSTGRES_USER=kolia
POSTGRES_PASSWORD=kolia

OLLAMA_MODEL=qwen2.5:3b

NUM_CTX=32768
MAX_TOKENS_ENTRADA_BLOCO=2500
OVERLAP_TOKENS=200
TOKENS_RESPOSTA_BLOCO=4096
TOKENS_RESPOSTA_CONSOLIDACAO=4096
```

Esse arquivo deixa as configs principais centralizadas.

---

## 6. Docker Compose

Arquivo:

```txt
infra/docker-compose.yml
```

Conteúdo recomendado:

```yaml
services:
  frontend:
    container_name: kolia-frontend
    build:
      context: ../frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:8080
    depends_on:
      - backend
    networks:
      - kolia-network
    restart: unless-stopped

  backend:
    container_name: kolia-backend
    build:
      context: ../back
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/${POSTGRES_DB:-kolia}
      SPRING_DATASOURCE_USERNAME: ${POSTGRES_USER:-kolia}
      SPRING_DATASOURCE_PASSWORD: ${POSTGRES_PASSWORD:-kolia}
      IA_SERVICE_URL: http://ia-service:3000
    depends_on:
      - postgres
      - ia-service
    networks:
      - kolia-network
    restart: unless-stopped

  ia-service:
    container_name: kolia-ia-service
    build:
      context: ../IA
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      PORT: 3000
      OLLAMA_URL: http://ollama:11434/api/generate
      MODEL: ${OLLAMA_MODEL:-qwen2.5:3b}
      NUM_CTX: ${NUM_CTX:-32768}
      MAX_TOKENS_ENTRADA_BLOCO: ${MAX_TOKENS_ENTRADA_BLOCO:-2500}
      OVERLAP_TOKENS: ${OVERLAP_TOKENS:-200}
      TOKENS_RESPOSTA_BLOCO: ${TOKENS_RESPOSTA_BLOCO:-4096}
      TOKENS_RESPOSTA_CONSOLIDACAO: ${TOKENS_RESPOSTA_CONSOLIDACAO:-4096}
    volumes:
      - ../IA/logs:/app/logs
    depends_on:
      - ollama
    networks:
      - kolia-network
    restart: unless-stopped

  ollama:
    container_name: kolia-ollama
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - kolia-network
    restart: unless-stopped

  postgres:
    container_name: kolia-postgres
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-kolia}
      POSTGRES_USER: ${POSTGRES_USER:-kolia}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kolia}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - kolia-network
    restart: unless-stopped

networks:
  kolia-network:
    driver: bridge

volumes:
  postgres_data:
  ollama_data:
```

---

## 7. Init do Postgres

Arquivo:

```txt
infra/postgres/init.sql
```

Conteúdo:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Esse arquivo ativa o pgvector no banco.

---

## 8. Dockerfile do Frontend

Arquivo:

```txt
frontend/Dockerfile
```

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## 9. Dockerfile do Backend

Arquivo:

```txt
back/Dockerfile
```

Para Spring Boot com Maven:

```dockerfile
FROM maven:3.9-eclipse-temurin-21

WORKDIR /app

COPY pom.xml ./

RUN mvn dependency:go-offline

COPY src ./src

EXPOSE 8080

CMD ["mvn", "spring-boot:run"]
```

Caso o projeto use Gradle, trocar por um Dockerfile com Gradle.

---

## 10. Dockerfile da IA

Arquivo:

```txt
IA/Dockerfile
```

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

RUN mkdir -p logs

EXPOSE 3000

CMD ["node", "server.js"]
```

---

## 11. Ajuste importante no `IA/package.json`

Como os scripts e seu serviço usam `import`, o `package.json` da pasta `IA/` precisa ter:

```json
{
  "type": "module",
  "scripts": {
    "start": "node server.js"
  }
}
```

Exemplo mais completo:

```json
{
  "name": "kolia-ia-service",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.18.0",
    "gpt-tokenizer": "^2.9.0"
  }
}
```

---

## 12. Script para instalar modelo

Arquivo:

```txt
infra/scripts/install-model.js
```

```js
import { spawnSync } from "node:child_process";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const INFRA_DIR = path.resolve(__dirname, "..");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: INFRA_DIR,
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

const argModel = process.argv[2];

let modelName = argModel;

if (!modelName) {
  const rl = readline.createInterface({ input, output });

  console.log("Digite o nome do modelo para instalar no Ollama:");
  console.log("Exemplos:");
  console.log("- qwen2.5:3b");
  console.log("- llama3.2:3b");
  console.log("- mistral");
  console.log("");

  modelName = await rl.question("Modelo: ");
  rl.close();
}

modelName = modelName.trim();

if (!modelName) {
  console.error("Nome do modelo não pode ser vazio.");
  process.exit(1);
}

console.log("Subindo Ollama, se necessário...");
run("docker", ["compose", "up", "-d", "ollama"]);

console.log(`Instalando modelo: ${modelName}`);
run("docker", ["compose", "exec", "-T", "ollama", "ollama", "pull", modelName]);

console.log("");
console.log("Modelos instalados:");
run("docker", ["compose", "exec", "-T", "ollama", "ollama", "list"]);
```

---

## 13. Script para deletar modelo

Arquivo:

```txt
infra/scripts/delete-model.js
```

```js
import { spawnSync } from "node:child_process";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const INFRA_DIR = path.resolve(__dirname, "..");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: INFRA_DIR,
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function capture(command, args) {
  const result = spawnSync(command, args, {
    cwd: INFRA_DIR,
    encoding: "utf-8",
    shell: process.platform === "win32"
  });

  if (result.status !== 0) {
    console.error(result.stderr || result.stdout);
    process.exit(result.status ?? 1);
  }

  return result.stdout;
}

console.log("Modelos instalados no Ollama:");

const list = capture("docker", [
  "compose",
  "exec",
  "-T",
  "ollama",
  "ollama",
  "list"
]);

console.log(list);

const rl = readline.createInterface({ input, output });

let modelName = await rl.question("Digite o nome do modelo para deletar: ");
modelName = modelName.trim();

if (!modelName) {
  console.error("Nome do modelo não pode ser vazio.");
  rl.close();
  process.exit(1);
}

const confirm = await rl.question(
  `Tem certeza que quer deletar '${modelName}'? Digite 'sim': `
);

rl.close();

if (confirm.trim().toLowerCase() !== "sim") {
  console.log("Operação cancelada.");
  process.exit(0);
}

console.log(`Deletando modelo: ${modelName}`);
run("docker", ["compose", "exec", "-T", "ollama", "ollama", "rm", modelName]);

console.log("");
console.log("Modelos restantes:");
run("docker", ["compose", "exec", "-T", "ollama", "ollama", "list"]);
```

---

## 14. Script principal para subir o projeto

Arquivo:

```txt
infra/scripts/start-dev.js
```

Esse script:

- Detecta Windows, Linux ou macOS
- Verifica se Docker Compose existe
- Pergunta qual modelo usar
- Sobe o Ollama
- Verifica se o modelo já está instalado
- Instala o modelo se estiver faltando
- Sobe todos os containers
- Mostra os comandos de log

```js
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const INFRA_DIR = path.resolve(__dirname, "..");

const DEFAULT_MODEL = process.env.OLLAMA_MODEL || "qwen2.5:3b";

const platform = os.platform();

function getPlatformName() {
  if (platform === "win32") return "Windows";
  if (platform === "linux") return "Linux";
  if (platform === "darwin") return "macOS";
  return platform;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: INFRA_DIR,
    stdio: "inherit",
    shell: platform === "win32",
    ...options
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function capture(command, args) {
  const result = spawnSync(command, args, {
    cwd: INFRA_DIR,
    encoding: "utf-8",
    shell: platform === "win32"
  });

  if (result.status !== 0) {
    return "";
  }

  return result.stdout;
}

function dockerComposeAvailable() {
  const result = spawnSync("docker", ["compose", "version"], {
    cwd: INFRA_DIR,
    encoding: "utf-8",
    shell: platform === "win32"
  });

  return result.status === 0;
}

function modelExists(modelName) {
  const output = capture("docker", [
    "compose",
    "exec",
    "-T",
    "ollama",
    "ollama",
    "list"
  ]);

  return output
    .split("\n")
    .map((line) => line.trim().split(/\s+/)[0])
    .includes(modelName);
}

async function askModelName() {
  const rl = readline.createInterface({ input, output });

  const answer = await rl.question(
    `Modelo padrão é '${DEFAULT_MODEL}'. Pressione Enter para usar ele ou digite outro: `
  );

  rl.close();

  return answer.trim() || DEFAULT_MODEL;
}

console.log("====================================");
console.log("KOLIA - START DEV");
console.log("====================================");
console.log(`Sistema detectado: ${getPlatformName()}`);
console.log(`Pasta infra: ${INFRA_DIR}`);
console.log("");

if (!dockerComposeAvailable()) {
  console.error("Docker Compose não encontrado.");
  console.error("Verifique se o Docker Desktop/Docker Engine está instalado e rodando.");
  process.exit(1);
}

const modelName = await askModelName();

console.log("");
console.log("Subindo container do Ollama...");
run("docker", ["compose", "up", "-d", "ollama"]);

console.log("");
console.log(`Verificando se o modelo '${modelName}' já está instalado...`);

if (!modelExists(modelName)) {
  console.log(`Modelo '${modelName}' não encontrado.`);
  console.log("Chamando script de instalação...");

  run("node", [path.join("scripts", "install-model.js"), modelName]);
} else {
  console.log(`Modelo '${modelName}' já está instalado.`);
}

console.log("");
console.log("Subindo todos os containers...");
run("docker", ["compose", "up", "-d", "--build"]);

console.log("");
console.log("Containers rodando:");
run("docker", ["compose", "ps"]);

console.log("");
console.log("Para ver logs:");
console.log("cd infra");
console.log("docker compose logs -f frontend");
console.log("docker compose logs -f backend");
console.log("docker compose logs -f ia-service");
console.log("docker compose logs -f ollama");
console.log("docker compose logs -f postgres");
```

---

## 15. Como rodar

Da raiz do projeto:

```bash
node infra/scripts/start-dev.js
```

Ou de dentro da pasta `infra`:

```bash
node scripts/start-dev.js
```

---

## 16. Instalar modelo manualmente

```bash
node infra/scripts/install-model.js
```

Ou passando o modelo direto:

```bash
node infra/scripts/install-model.js qwen2.5:3b
```

---

## 17. Deletar modelo

```bash
node infra/scripts/delete-model.js
```

---

## 18. Subir com outro modelo

### Linux/macOS

```bash
OLLAMA_MODEL=llama3.2:3b node infra/scripts/start-dev.js
```

### Windows PowerShell

```powershell
$env:OLLAMA_MODEL="llama3.2:3b"
node infra/scripts/start-dev.js
```

---

## 19. Logs separados

Executar dentro da pasta `infra`:

```bash
docker compose logs -f frontend
docker compose logs -f backend
docker compose logs -f ia-service
docker compose logs -f ollama
docker compose logs -f postgres
```

Para ver os últimos logs sem seguir em tempo real:

```bash
docker compose logs --tail=100 frontend
docker compose logs --tail=100 backend
docker compose logs --tail=100 ia-service
docker compose logs --tail=100 ollama
docker compose logs --tail=100 postgres
```

Para logs com timestamp:

```bash
docker compose logs -f -t ia-service
```

---

## 20. Comandos úteis

Subir tudo manualmente:

```bash
cd infra
docker compose up -d --build
```

Subir apenas um serviço:

```bash
cd infra
docker compose up -d postgres
docker compose up -d ollama
docker compose up -d ia-service
docker compose up -d backend
docker compose up -d frontend
```

Parar tudo:

```bash
cd infra
docker compose down
```

Parar e apagar volumes:

```bash
cd infra
docker compose down -v
```

Atenção: `docker compose down -v` apaga os dados do Postgres e os modelos baixados do Ollama.

Listar containers:

```bash
cd infra
docker compose ps
```

Rebuildar apenas o backend:

```bash
cd infra
docker compose up -d --build backend
```

Rebuildar apenas a IA:

```bash
cd infra
docker compose up -d --build ia-service
```

Rebuildar apenas o frontend:

```bash
cd infra
docker compose up -d --build frontend
```

Entrar no container da IA:

```bash
cd infra
docker compose exec ia-service sh
```

Entrar no container do backend:

```bash
cd infra
docker compose exec backend sh
```

Entrar no Postgres:

```bash
cd infra
docker compose exec postgres psql -U kolia -d kolia
```

Listar modelos do Ollama:

```bash
cd infra
docker compose exec ollama ollama list
```

Rodar modelo no Ollama:

```bash
cd infra
docker compose exec ollama ollama run qwen2.5:3b
```

---

## 21. Testes rápidos de saúde

### Testar frontend

Acessar no navegador:

```txt
http://localhost:5173
```

### Testar backend

```bash
curl http://localhost:8080
```

Se o backend tiver rota `/health`:

```bash
curl http://localhost:8080/health
```

### Testar IA Service

```bash
curl http://localhost:3000
```

### Testar Ollama

```bash
curl http://localhost:11434/api/tags
```

### Testar Postgres

```bash
cd infra
docker compose exec postgres psql -U kolia -d kolia -c "SELECT version();"
```

Testar pgvector:

```bash
cd infra
docker compose exec postgres psql -U kolia -d kolia -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

---

## 22. Fluxo de desenvolvimento recomendado

### Primeira vez rodando

```bash
node infra/scripts/start-dev.js
```

Ele vai:

1. Detectar o sistema operacional.
2. Validar Docker Compose.
3. Perguntar o modelo.
4. Subir o Ollama.
5. Verificar se o modelo existe.
6. Instalar se não existir.
7. Subir todos os serviços.
8. Mostrar comandos de log.

### Desenvolvimento diário

```bash
cd infra
docker compose up -d
docker compose logs -f ia-service
```

### Quando mudar código da IA

```bash
cd infra
docker compose up -d --build ia-service
docker compose logs -f ia-service
```

### Quando mudar backend

```bash
cd infra
docker compose up -d --build backend
docker compose logs -f backend
```

### Quando mudar frontend

```bash
cd infra
docker compose up -d --build frontend
docker compose logs -f frontend
```

---

## 23. Integração entre serviços

Dentro da rede Docker, os containers se comunicam pelo nome do serviço.

### Frontend

O frontend roda no navegador do usuário, então ele chama o backend via:

```txt
http://localhost:8080
```

### Backend

O backend chama a IA Service via:

```txt
http://ia-service:3000
```

O backend chama o Postgres via:

```txt
postgres:5432
```

### IA Service

A IA Service chama o Ollama via:

```txt
http://ollama:11434/api/generate
```

---

## 24. Configuração no Backend Spring Boot

No `application.properties` ou `application.yml`, usar variáveis de ambiente.

### `application.properties`

```properties
spring.datasource.url=${SPRING_DATASOURCE_URL}
spring.datasource.username=${SPRING_DATASOURCE_USERNAME}
spring.datasource.password=${SPRING_DATASOURCE_PASSWORD}

ia.service.url=${IA_SERVICE_URL}
```

### Exemplo de chamada para IA Service

O backend deve chamar:

```txt
POST http://ia-service:3000/analisar
```

Body:

```json
{
  "transcricao": "texto da transcrição aqui"
}
```

---

## 25. Configuração no Frontend Vite

No frontend, a variável:

```env
VITE_API_URL=http://localhost:8080
```

Exemplo de uso:

```js
const API_URL = import.meta.env.VITE_API_URL;

const response = await fetch(`${API_URL}/meetings`);
```

---

## 26. Observações importantes

- O `docker-compose.yml` fica dentro da pasta `infra`.
- Por isso os caminhos dos builds usam `../frontend`, `../back` e `../IA`.
- O container `ia-service` chama o Ollama usando `http://ollama:11434/api/generate`.
- O backend chama a IA usando `http://ia-service:3000`.
- O backend chama o banco usando `postgres:5432`.
- O frontend no navegador usa `http://localhost:8080` para chamar o backend.
- Os modelos do Ollama ficam salvos no volume `ollama_data`.
- Os dados do Postgres ficam salvos no volume `postgres_data`.
- Os logs da IA ficam mapeados em `IA/logs`.
- O Ollama deve rodar separado da IA Service.
- A pasta `IA/` guarda o código Node que chama o Ollama.
- O container `ollama` guarda e executa os modelos.
- O backend deve ser o dono das regras de permissão e persistência.
- O frontend não deve chamar IA nem banco diretamente.

---

## 27. Problemas comuns e soluções

### 27.1 Docker Compose não encontrado

Erro:

```txt
Docker Compose não encontrado.
```

Solução:

```bash
docker compose version
```

Se não funcionar, instalar Docker Desktop no Windows/macOS ou Docker Engine + Compose no Linux.

---

### 27.2 Porta já em uso

Erro comum:

```txt
port is already allocated
```

Verificar quem está usando a porta.

Linux/macOS:

```bash
sudo lsof -i :8080
sudo lsof -i :3000
sudo lsof -i :5173
sudo lsof -i :11434
sudo lsof -i :5432
```

Windows PowerShell:

```powershell
netstat -ano | findstr :8080
netstat -ano | findstr :3000
netstat -ano | findstr :5173
netstat -ano | findstr :11434
netstat -ano | findstr :5432
```

Alternativas:

- parar o processo que está usando a porta
- mudar a porta no `docker-compose.yml`

---

### 27.3 IA Service não encontra o Ollama

Verificar se a env está correta:

```txt
OLLAMA_URL=http://ollama:11434/api/generate
```

Ver logs:

```bash
cd infra
docker compose logs -f ia-service
docker compose logs -f ollama
```

Testar dentro do container da IA:

```bash
cd infra
docker compose exec ia-service sh
```

Dentro dele:

```sh
wget -qO- http://ollama:11434/api/tags
```

---

### 27.4 Modelo não encontrado

Erro comum:

```txt
model not found
```

Instalar modelo:

```bash
node infra/scripts/install-model.js qwen2.5:3b
```

Ou dentro da pasta `infra`:

```bash
docker compose exec ollama ollama pull qwen2.5:3b
```

---

### 27.5 Backend não conecta no Postgres

Verificar variáveis:

```txt
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/kolia
SPRING_DATASOURCE_USERNAME=kolia
SPRING_DATASOURCE_PASSWORD=kolia
```

Ver logs:

```bash
cd infra
docker compose logs -f backend
docker compose logs -f postgres
```

Testar Postgres:

```bash
cd infra
docker compose exec postgres psql -U kolia -d kolia -c "SELECT 1;"
```

---

### 27.6 Frontend não consegue chamar backend

Verificar se o frontend está usando:

```txt
VITE_API_URL=http://localhost:8080
```

Importante:

- frontend roda no browser
- browser não entende `http://backend:8080`
- `http://backend:8080` só funciona entre containers
- no browser tem que usar `http://localhost:8080`

---

### 27.7 Alterei Dockerfile mas nada mudou

Rodar rebuild:

```bash
cd infra
docker compose up -d --build nome-do-servico
```

Exemplo:

```bash
docker compose up -d --build ia-service
```

---

### 27.8 Apagar tudo e começar do zero

```bash
cd infra
docker compose down -v
docker compose up -d --build
```

Atenção: isso apaga banco e modelos.

---

## 28. Checklist de implementação

### Estrutura

- [ ] Criar pasta `frontend/`
- [ ] Criar pasta `back/`
- [ ] Criar pasta `IA/`
- [ ] Criar pasta `infra/`
- [ ] Criar pasta `infra/scripts/`
- [ ] Criar pasta `infra/postgres/`
- [ ] Criar pasta `IA/logs/`

### Docker

- [ ] Criar `frontend/Dockerfile`
- [ ] Criar `back/Dockerfile`
- [ ] Criar `IA/Dockerfile`
- [ ] Criar `infra/docker-compose.yml`
- [ ] Criar `infra/.env`
- [ ] Criar `infra/postgres/init.sql`

### Scripts

- [ ] Criar `infra/scripts/start-dev.js`
- [ ] Criar `infra/scripts/install-model.js`
- [ ] Criar `infra/scripts/delete-model.js`

### Testes

- [ ] Rodar `node infra/scripts/start-dev.js`
- [ ] Verificar `docker compose ps`
- [ ] Testar frontend em `localhost:5173`
- [ ] Testar backend em `localhost:8080`
- [ ] Testar IA em `localhost:3000`
- [ ] Testar Ollama em `localhost:11434/api/tags`
- [ ] Testar Postgres com `SELECT 1`
- [ ] Ver logs separados por serviço

---

## 29. Próximos passos técnicos

Depois que a infra básica estiver rodando, os próximos passos recomendados são:

1. Criar endpoint no backend para upload ou envio da transcrição.
2. Backend criar registro da reunião no Postgres.
3. Backend chamar `POST /analisar` da IA Service.
4. IA Service retornar JSON estruturado.
5. Backend salvar relatório final no Postgres.
6. Criar tela no frontend para visualizar relatório.
7. Adicionar status de processamento:
   - `PENDING`
   - `PROCESSING`
   - `DONE`
   - `FAILED`
8. Depois adicionar embeddings com pgvector.
9. Depois adicionar perguntas sobre reuniões usando busca semântica.
10. Depois evoluir para processamento assíncrono com fila.

---

## 30. Possível modelagem inicial do banco

Exemplo simples para MVP:

```sql
CREATE TABLE IF NOT EXISTS meetings (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  user_id UUID,
  status TEXT NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meeting_reports (
  id UUID PRIMARY KEY,
  meeting_id UUID REFERENCES meetings(id),
  report_json JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meeting_chunks (
  id UUID PRIMARY KEY,
  meeting_id UUID REFERENCES meetings(id),
  chunk_index INT NOT NULL,
  content TEXT,
  summary TEXT,
  metadata JSONB,
  embedding vector(768),
  created_at TIMESTAMP DEFAULT NOW()
);
```

A dimensão do vetor `vector(768)` depende do modelo de embedding usado. Ajustar depois conforme o modelo escolhido.

---

## 31. Evolução futura da arquitetura

Para MVP:

```txt
Frontend → Backend → IA Service → Ollama
Backend → Postgres
```

Depois, quando crescer:

```txt
Frontend
   ↓
Backend
   ↓
Queue/Worker
   ↓
IA Service
   ↓
Ollama

Backend/Worker → Postgres + pgvector
```

Possíveis melhorias futuras:

- Nginx reverse proxy
- Fila com Redis ou RabbitMQ
- Worker separado para análise
- Storage para transcrições brutas
- Backup automático do Postgres
- Healthchecks no Docker Compose
- Ambiente separado para produção
- Deploy em VPS
- Observabilidade com logs estruturados

---

## 32. Conclusão

A estrutura recomendada separa bem as responsabilidades:

```txt
frontend/  → interface Vite
back/      → API Spring Boot, auth, regras e banco
IA/        → serviço Node que processa transcrições
infra/     → Docker Compose, banco, scripts e configuração de ambiente
```

Essa separação deixa o projeto mais organizado, facilita debug por logs e permite evoluir a IA sem bagunçar o backend principal.
