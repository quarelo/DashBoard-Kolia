# Docker Compose simples do Kolia

## Objetivo

Organizar o ambiente local para que cada serviço tenha seu próprio container e seus próprios logs, mantendo um único `docker-compose.yml` na raiz e um único comando de inicialização.

O ambiente é exclusivamente de desenvolvimento neste momento. Backend e IA ainda estão incompletos e não devem aparentar estar prontos.

## Arquitetura

O Compose principal terá cinco serviços na rede interna `kolia-network`:

- `frontend`: aplicação Vite na porta `5173`;
- `backend`: placeholder isolado na porta `8080` até o código real existir;
- `ia-service`: aplicação FastAPI na porta `3000`, carregada de `src.app.main`;
- `postgres`: PostgreSQL com pgvector, persistido em volume e publicado na porta local `5433`;
- `ollama`: servidor local de modelos, persistido em volume e publicado na porta `11434`.

Cada serviço de aplicação continuará com seu próprio Dockerfile. Os arquivos Compose duplicados em `infra/` e `ia/` serão removidos; arquivos auxiliares, como a inicialização do Postgres, continuarão nas respectivas pastas.

## Inicialização e comunicação

O ambiente inteiro será construído e iniciado na raiz com:

```sh
docker compose up --build
```

Dentro da rede Docker:

- o frontend usa o backend como API pública configurada para o navegador em `http://localhost:8080`;
- o backend recebe a URL interna da IA como `http://ia-service:3000`;
- o backend recebe a URL interna do banco como `postgres:5432`;
- a IA recebe a URL interna do Ollama como `http://ollama:11434`.

Os serviços não terão dependências artificiais que impeçam componentes independentes de subir. Healthchecks serão usados onde já existe uma verificação real, sem declarar o backend placeholder como aplicação saudável.

## Logs e persistência

Os logs permanecem separados pelo próprio Docker Compose:

```sh
docker compose logs -f frontend
docker compose logs -f backend
docker compose logs -f ia-service
```

Postgres e Ollama usam volumes nomeados. A IA pode manter a pasta local de logs montada quando ela existir, sem incorporar logs à imagem.

## Tratamento dos serviços incompletos

O backend continuará como placeholder explícito e manterá o container ativo, permitindo que seu log informe que ainda não há aplicação. Ele será substituído pelo build real quando o código Spring Boot for adicionado.

A IA já possui uma aplicação FastAPI mínima em `ia/src/app/main.py`. O Dockerfile será ajustado para esse caminho, preservando as alterações locais existentes e sem inventar funcionalidades ainda não implementadas.

## Validação

A entrega será validada por:

1. renderização do Compose com `docker compose config`;
2. construção das imagens locais com `docker compose build`;
3. inicialização dos serviços com `docker compose up`;
4. inspeção do estado e dos logs por serviço;
5. chamada ao healthcheck disponível da IA e verificação de prontidão do Postgres.

O critério de sucesso é que um único comando suba containers separados, com configuração válida e logs individualmente acessíveis, respeitando que backend e IA ainda são parciais.
