# KOLIA — Frontend

Interface do KOLIA: login, dashboard executivo, lista e detalhe das reuniões
analisadas, exclusão e chat por reunião. Consome só a API do backend; não fala com
o serviço de IA nem usa dados fixos.

**Stack:** React 19, TypeScript, Vite, Tailwind CSS, React Router, Recharts e Radix
UI.

## Rodar

Pelo Docker Compose, da raiz do repositório, como o resto do projeto:

```bash
make dev-detached
```

A aplicação fica em `http://localhost:5173`. `./frontend` é montado no container
com hot reload, então editar os arquivos já atualiza a página. Não rode
`npm run dev` no host: ver o `CLAUDE.md` da raiz.

`VITE_API_URL` é o endereço do backend visto pelo navegador. O Compose define
`http://localhost:8080`, e sem a variável o código usa esse mesmo valor.

## Páginas

| Rota | O que mostra | API |
| --- | --- | --- |
| `/` | Página inicial | — |
| `/login`, `/register` | Entrar e criar conta | `POST /login`, `POST /register`, `GET /me` |
| `/app/dashboard` | Dashboard executivo: KPIs, comparativos e top 5, com filtro de UF e segmento | `GET /api/dashboard/executive` |
| `/app/meetings` | Reuniões analisadas, com exclusão | `GET /api/dashboard/meetings`, `DELETE /api/dashboard/meetings/{id}` |
| `/app/meetings/:id` | Resumo da IA, grade de metadados do CSV, transcrição, chat e exclusão | `GET /api/dashboard/meetings/{id}` |
| `/app/insights` | Visão agregada, montada no navegador a partir de até 60 análises | lista + detalhe |
| `/app/chat` | Escolhe uma reunião e lista as conversas dela: reabre uma anterior ou começa uma nova, sem apagar as outras | `GET /api/dashboard/meetings/{id}/chat/conversations`, `POST /api/dashboard/meetings/{id}/chat` |

A grade de metadados e a transcrição só aparecem em reuniões que entraram pelo
import do backend. Uma análise enviada direto à IA aparece sem elas. O chat abre
quando a análise chega a `DONE`.

## Estrutura

```text
src/
├── App.tsx            rotas
├── pages/             uma página por rota
├── components/        auth, layout, meetings (ex.: DeleteMeetingDialog), ui
├── context/           AuthContext: sessão do usuário
├── services/          authService, dashboardService, chatService
└── lib/api.ts         apiRequest: URL base, token e mensagens de erro
```

O token JWT fica no `localStorage` (`kolia.token`) e vai como `Bearer` em cada
chamada. Quando a API devolve `detail.message`, a interface mostra essa mensagem
em vez do código HTTP.

## Qualidade

```bash
make test-frontend   # npm run lint && npm run build
```

O build roda `tsc -b` antes do Vite, então erro de tipo quebra o build.
