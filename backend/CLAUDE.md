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

There are no `__init__.py` files — modules import each other with flat paths (`from core.config import settings`, `from models.user import UserModel`, etc.), so the app must be run with `backend/` as the working directory / on `sys.path` (e.g. `uvicorn ...` invoked from inside `backend/`).

## Entrypoint

`main.py` owns the FastAPI app, CORS and lifespan. `routers/auth.py` is now an `APIRouter`; `/register` and `/login` paths are preserved. `routers/meetings.py` owns `/api/imports` and `/api/meetings`. Schema initialization runs in the app lifespan, not on router import.

## Data model

- `core.users` (schema `core`, table `users`): `id`, `name`, `email` (unique), `role` (`RoleEnum`: `SALES_DIRECTOR` | `USER`), `password` (bcrypt hash).
- `core.meetings` carries a `version` column, unique per `(owner_id, external_id, version)`. Re-importing a known `external_id` with a different transcription writes a **new version** instead of the previous `409 MEETING_CONFLICT`, which had left no way to ingest a corrected transcript at all. The superseded row keeps its transcription and its `analysis_id`, so its chunks, embeddings and citations stay valid. The IA needed no change: its idempotency key is derived from the internal UUID plus the transcription hash, and each version is a new row, so it naturally gets its own analysis. `MeetingImport.versioned_count` reports how many rows a batch revised. Content already stored under that id in *any* version is skipped rather than re-versioned, so an A → B → A cycle does not grow a version per upload.
- `main.py` calls `database.init_database()` in its lifespan. This creates the `core` schema before `Base.metadata.create_all` and registers users, imports and meetings. Versioned migrations remain pending.
- `create_all()` only CREATEs — it never ALTERs an existing table. A database created before versioning therefore keeps the old shape, `init_database()` reports no error, and the app then fails at runtime on the missing `version` column (verified). `infra/postgres/migrations/001_meeting_versions.sql` is the stopgap for those databases: it adds both columns, drops the old `(owner_id, external_id)` unique constraint whatever it was named, and adds the three-column one. It is idempotent and a no-op on a database create_all() built fresh. This is exactly the gap Alembic should close.

## Auth flow

- `POST /register` — 201 on success, 400 if email already exists. Hashes password with bcrypt via `passlib`. Password is validated at the schema layer to be 8–72 chars (`schemas/user.py`) — 72 is bcrypt's hard byte limit; passlib raises `ValueError` past that instead of truncating, so this guard prevents a 500 on long passwords.
- `POST /login` — verifies password, returns `{access_token, token_type, expires_in_days}` where `expires_in_days` is read from `settings.access_token_expire_days` (previously hardcoded to `7`, which would silently drift from the real token `exp` if `ACCESS_TOKEN_EXPIRE_DAYS` were ever changed). JWT payload is `{sub: email, role, exp}`, signed HS256.
- `core/auth.py` verifies JWT signature, expiration and subject, resolves the user and protects import/meeting routes. All meeting queries scope by owner.
- CORS defaults to `http://localhost:5173`; `CORS_ORIGINS` accepts a JSON array of allowed origins.

## Config / secrets

- There is **one** `.env`, at the repo root, next to `docker-compose.yml`. `core/config.py` resolves it by absolute path (`ROOT_ENV`), so it does not matter which directory uvicorn runs from. The per-service `backend/.env` and `ia/.env` are gone: three files for one system meant the same setting could disagree with itself, and it did — `backend/.env` had shipped `DATABASE_URL=DATABASE_URL=postgresql+psycopg2://...`, the key pasted into its own value, which SQLAlchemy rejects outright (`Could not parse SQLAlchemy URL`). The test suites never caught it because they override `DATABASE_URL`.
- The root file uses the names Compose already interpolates, so `Settings.secret_key` accepts either spelling via `AliasChoices("SECRET_KEY", "JWT_SECRET")`; the IA does the same for `MODEL`/`OLLAMA_MODEL` and friends. Inside a container `ROOT_ENV` does not exist, which pydantic-settings ignores, and Compose passes the same values as real environment variables — those outrank any file, so the container gets `postgres:5432` while a local run gets the `localhost:5433` in the file.
- `Settings.database_url` and `Settings.secret_key` have **no defaults** — they're required. Previously both had hardcoded fallbacks baked into source (including a real-looking secret key); a missing/misconfigured `.env` now fails loudly at startup instead of silently running with an insecure default.
- The root `.env` is gitignored — don't commit it; `.env.example` mirrors it key-for-key with the secrets blanked. There was no `backend/.dockerignore`, so a stray `.env` would get baked into the built image via the Dockerfile's `COPY . .`; added `backend/.dockerignore` to exclude it.
- `docker-compose.yml`'s `backend` service used to inject `SPRING_DATASOURCE_URL`/`SPRING_DATASOURCE_USERNAME`/`SPRING_DATASOURCE_PASSWORD` — dead leftovers from an earlier Spring Boot plan (see `context/plano-infra-docker-kolia-completo.md`). Replaced with `DATABASE_URL` (built from `POSTGRES_*`, same pattern as the `ia-service` block) and `SECRET_KEY: ${JWT_SECRET:?...}`, sourced from the root `.env`'s `JWT_SECRET`. That root variable did not actually exist — the root `.env` defined `SECRET_KEY`, a name Compose never reads — so both services received an empty `SECRET_KEY`. PyJWT refuses an empty HMAC key with `InvalidKeyError`, which is *not* a subclass of `InvalidTokenError`, so `get_current_user`'s handler did not catch it: `/login` and every authenticated request returned **500**, not 401. Renamed the root variable to `JWT_SECRET`, added the `:?` guard so `docker compose up` fails with a clear message instead of booting, and gave `Settings.secret_key` a `min_length=32` so a short/empty key fails at startup rather than per request.
- `requirements.txt` had no version pins; pinned `passlib[bcrypt]==1.7.4` + `bcrypt==4.0.1` because `bcrypt>=4.1` dropped the `__about__.__version__` attribute that `passlib` 1.7.4 (its last release) reads to detect the backend — a widely-hit break for this exact combination.

## Running locally

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

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
