# Backend — CLAUDE.md

This is the KOLIA **backend** service: Python/FastAPI with login/auth, CSV/JSON meeting imports, owner-scoped meeting queries and idempotent analysis dispatch to IA. See `docs/meeting-import-flow.md` in the repository root for the import contract and test commands.

## Stack

- **FastAPI** for the HTTP layer
- **SQLAlchemy** (declarative, sync engine) against **Postgres**
- **passlib[bcrypt]** for password hashing
- **PyJWT** for token issuance (HS256)
- **pydantic-settings** for config, loaded from `.env`

## Layout

```
backend/
├── core/
│   ├── config.py     # Settings (pydantic-settings), reads the repo-root .env
│   ├── database.py   # engine, SessionLocal, Base, get_db(), init_database()
│   └── security.py   # password hashing + create_access_token()
├── models/
│   └── user.py        # UserModel (SQLAlchemy) — table core.users
├── schemas/
│   └── user.py         # UserCreate, UserLogin, Token, RoleEnum (Pydantic)
├── routers/
│   └── auth.py          # currently owns the FastAPI() app instance + /register, /login
├── requirements.txt
├── Dockerfile
└── .env.example
```

There are no `__init__.py` files — modules import each other with flat paths (`from core.config import settings`, `from models.user import UserModel`, etc.), so the app must run with `backend/` as the working directory / on `sys.path`. The image's `WORKDIR /app` is that directory, which is why the container just works.

## Entrypoint

`main.py` owns the FastAPI app, CORS and lifespan. `routers/auth.py` is now an `APIRouter`; `/register` and `/login` paths are preserved. `routers/meetings.py` owns `/api/imports` and `/api/meetings`. Schema initialization runs in the app lifespan, not on router import.

## Data model

- `core.users` (schema `core`, table `users`): `id`, `name`, `email` (unique), `role` (`RoleEnum`: `SALES_DIRECTOR` | `USER`), `password` (bcrypt hash).
- `core.meetings` carries a `version` column, unique per `(owner_id, external_id, version)`. Re-importing a known `external_id` with a different transcription writes a **new version** instead of the previous `409 MEETING_CONFLICT`, which had left no way to ingest a corrected transcript at all. The superseded row keeps its transcription and its `analysis_id`, so its chunks, embeddings and citations stay valid. The IA needed no change: its idempotency key is derived from the internal UUID plus the transcription hash, and each version is a new row, so it naturally gets its own analysis. `MeetingImport.versioned_count` reports how many rows a batch revised. Content already stored under that id in *any* version is skipped rather than re-versioned, so an A → B → A cycle does not grow a version per upload.
- **All DDL lives in Alembic, in Python.** `backend/migrations/versions/` holds `0001_initial_schema` and `0002_meeting_versions`; the IA has its own five revisions and its own version table, in schema `ai`. There is no `.sql` file anywhere in the repo — `infra/postgres/init.sql` was deleted too, since `ia/migrations/env.py` and revision `0001` both issue `CREATE EXTENSION IF NOT EXISTS vector` (verified: migrating a virgin database with no init hook produces the extension at 0.8.6 and all five `ai` tables).
- `main.py` calls `database.init_database()` in its lifespan, but it no longer creates anything. `create_all()` only ever CREATEs — never ALTERs — so a database built before a column was added kept the old shape, reported no error, and failed at runtime on the missing `version` column (verified). `init_database()` now just compares the database's revision against `head` and refuses to boot when they differ, telling you to run `alembic upgrade head`. The container's command runs that migration before uvicorn, so a normal `docker compose up` is already migrated.

## Auth flow

- Routes are mounted under `/auth` (`/auth/register`, `/auth/login`, `/auth/me`).
- `GET /auth/me` — returns the current user (`id, name, email, role`); requires
  `Authorization: Bearer <token>`. `core/deps.py::get_current_user` decodes the JWT
  (`core/security.py::decode_access_token`), reads `sub` (email), loads the row; 401
  on missing/invalid/expired token or unknown user.
- `POST /register` — 201 on success, 400 if email already exists. Hashes password with bcrypt via `passlib`. Password is validated at the schema layer to be 8–72 chars (`schemas/user.py`) — 72 is bcrypt's hard byte limit; passlib raises `ValueError` past that instead of truncating, so this guard prevents a 500 on long passwords.
- `POST /login` — verifies password, returns `{access_token, token_type, expires_in_days}` where `expires_in_days` is read from `settings.access_token_expire_days` (previously hardcoded to `7`, which would silently drift from the real token `exp` if `ACCESS_TOKEN_EXPIRE_DAYS` were ever changed). JWT payload is `{sub: email, role, exp}`, signed HS256.
- `core/auth.py` verifies JWT signature, expiration and subject, resolves the user and protects import/meeting routes. All meeting queries scope by owner. `GET /me` (via `routers/auth.py`) returns the authenticated user and is the first consumer for the frontend session bootstrap.
- CORS defaults to `http://localhost:5173`; `CORS_ORIGINS` accepts a JSON array of allowed origins.

## Config / secrets

- There is **one** `.env`, at the repo root, next to `docker-compose.yml`. `core/config.py` resolves it by absolute path (`ROOT_ENV`), so the working directory does not matter. The per-service `backend/.env` and `ia/.env` are gone: three files for one system meant the same setting could disagree with itself, and it did — `backend/.env` had shipped `DATABASE_URL=DATABASE_URL=postgresql+psycopg2://...`, the key pasted into its own value, which SQLAlchemy rejects outright (`Could not parse SQLAlchemy URL`). The test suites never caught it because they override `DATABASE_URL`.
- The root file uses the names Compose already interpolates, so `Settings.secret_key` accepts either spelling via `AliasChoices("SECRET_KEY", "JWT_SECRET")`; the IA does the same for `MODEL`/`OLLAMA_MODEL` and friends. Inside a container `ROOT_ENV` does not exist, which pydantic-settings ignores, and Compose passes the same values as real environment variables — those outrank any file, so the container gets `postgres:5432` while a local run gets the `localhost:5433` in the file.
- `Settings.database_url` and `Settings.secret_key` have **no defaults** — they're required. Previously both had hardcoded fallbacks baked into source (including a real-looking secret key); a missing/misconfigured `.env` now fails loudly at startup instead of silently running with an insecure default.
- The root `.env` is gitignored — don't commit it; `.env.example` mirrors it key-for-key with the secrets blanked. There was no `backend/.dockerignore`, so a stray `.env` would get baked into the built image via the Dockerfile's `COPY . .`; added `backend/.dockerignore` to exclude it.
- `docker-compose.yml`'s `backend` service used to inject `SPRING_DATASOURCE_URL`/`SPRING_DATASOURCE_USERNAME`/`SPRING_DATASOURCE_PASSWORD` — dead leftovers from an earlier Spring Boot plan (see `context/plano-infra-docker-kolia-completo.md`). Replaced with `DATABASE_URL` (built from `POSTGRES_*`, same pattern as the `ia-service` block) and `SECRET_KEY: ${JWT_SECRET:?...}`, sourced from the root `.env`'s `JWT_SECRET`. That root variable did not actually exist — the root `.env` defined `SECRET_KEY`, a name Compose never reads — so both services received an empty `SECRET_KEY`. PyJWT refuses an empty HMAC key with `InvalidKeyError`, which is *not* a subclass of `InvalidTokenError`, so `get_current_user`'s handler did not catch it: `/login` and every authenticated request returned **500**, not 401. Renamed the root variable to `JWT_SECRET`, gave **both** the `backend` and `ia-service` blocks the `:?` guard so `docker compose up` fails with a clear message instead of booting, and gave `Settings.secret_key` a `min_length=32` so a short/empty key fails at startup rather than per request. Keep the two blocks identical: the `backend` one had drifted back to `${JWT_SECRET:-local-development-only-change-me}`, a fallback exactly 32 characters long, so it cleared `min_length` and the service would have signed real tokens with a secret published in the repo.
- `requirements.txt` had no version pins; pinned `passlib[bcrypt]==1.7.4` + `bcrypt==4.0.1` because `bcrypt>=4.1` dropped the `__about__.__version__` attribute that `passlib` 1.7.4 (its last release) reads to detect the backend — a widely-hit break for this exact combination.

## Running

**Always run through Docker Compose, from the repo root.** Never `uvicorn` on the
host, even for a quick check:

```bash
docker compose up -d --build
docker compose ps          # all five: postgres, ollama, ia-service, backend, frontend
```

`./backend` is bind-mounted and uvicorn runs with `--reload`, so editing a file
on the host reloads the container — a host run buys nothing and costs
correctness. The service names *are* the hostnames: the backend reaches the IA at
`http://ia-service:3000` and the IA reaches Ollama at `http://ollama:11434`.
Those names only resolve inside `kolia-network`.

Running one service on the host breaks that. With the IA started by hand on
`127.0.0.1:3000` while the rest was containerized, the backend resolved
`ia-service` to nothing (`ConnectError: Name or service not known`) and the
dashboard chat answered **503 `IA_UNAVAILABLE`** on every message — a
connectivity failure that reads like the IA being down. Binding the host process
to `0.0.0.0` would not have helped either: the container needs the name, not the
port.

If you must debug one service in isolation, bring the others up first and give it
the container's environment (`docker compose exec ia-service ...`) rather than
starting a parallel process on the host.

## Superuser bootstrap

`scripts/create_superuser.py` creates (or promotes, with `--force`) a user with
role `SALES_DIRECTOR` — the highest role `RoleEnum` defines; there is no separate
superuser flag. It calls `init_database()` first, so it works against an empty
database.

```bash
# From the repo root, with the stack up:
docker compose run --rm -e KOLIA_SUPERUSER_PASSWORD backend \
    python scripts/create_superuser.py --name "Ana" --email ana@empresa.com

# Or type the password interactively (no echo):
docker compose run --rm -it backend \
    python scripts/create_superuser.py --name "Ana" --email ana@empresa.com
```

The password comes from `KOLIA_SUPERUSER_PASSWORD` or an interactive prompt,
never from argv — a password in `--password` would land in shell history and in
`ps` output. It is validated to the same 8–72 character window as `/register`.
Email is lowercased before lookup and insert.

Via Docker Compose (from repo root):

```bash
docker compose up -d --build backend
```

Postgres runs as the `postgres` service in `docker-compose.yml` (image `pgvector/pgvector:pg16`, host port `5433`, container port `5432`).

## Sibling services (context, not owned by this folder)

- `frontend/` — Vite app, expects the backend at `http://localhost:8080`.
- `ia/` — separate FastAPI analysis/embedding service. The backend dispatches saved transcriptions through `IA_SERVICE_URL`, always with a persistent-content idempotency key. Upload alone never queues analysis. The existing React UI still uses fixtures; these new APIs are available through `/docs` for integration.
