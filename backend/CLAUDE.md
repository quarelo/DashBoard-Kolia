# Backend — CLAUDE.md

This is the KOLIA **backend** service: a Python/FastAPI app currently implementing the **login/auth feature** (registration, login, JWT issuance). It's early-stage — only the auth vertical slice exists so far.

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
│   ├── config.py     # Settings (pydantic-settings), reads backend/.env
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

## ⚠️ Known gap: no `main.py` yet

`routers/auth.py` currently instantiates `app = FastAPI()` directly and defines `/register` and `/login` on it — it's acting as the entrypoint, not a mountable `APIRouter`. But `Dockerfile`'s `CMD` runs `uvicorn main:app`, and there is **no `backend/main.py`**. The image as committed will not boot. Before adding more routers, this needs to be reconciled — most likely: turn `auth.py` into an `APIRouter`, add a `main.py` that creates the real `FastAPI()` app, includes the router, and calls `init_database()`/`Base.metadata.create_all`. Check with the user before assuming which direction to take this.

## Data model

- `core.users` (schema `core`, table `users`): `id`, `name`, `email` (unique), `role` (`RoleEnum`: `SALES_DIRECTOR` | `USER`), `password` (bcrypt hash).
- `routers/auth.py` calls `database.init_database()` at import time, which creates the `core` schema (`CREATE SCHEMA IF NOT EXISTS core`) before `Base.metadata.create_all` — this used to be skipped (raw `create_all` without the schema step), which would fail on a fresh Postgres with `InvalidSchemaName`; fixed.

## Auth flow

- `POST /register` — 201 on success, 400 if email already exists. Hashes password with bcrypt via `passlib`. Password is validated at the schema layer to be 8–72 chars (`schemas/user.py`) — 72 is bcrypt's hard byte limit; passlib raises `ValueError` past that instead of truncating, so this guard prevents a 500 on long passwords.
- `POST /login` — verifies password, returns `{access_token, token_type, expires_in_days}` where `expires_in_days` is read from `settings.access_token_expire_days` (previously hardcoded to `7`, which would silently drift from the real token `exp` if `ACCESS_TOKEN_EXPIRE_DAYS` were ever changed). JWT payload is `{sub: email, role, exp}`, signed HS256.
- There is **no dependency yet to decode/verify a token** (no `get_current_user`), so nothing downstream can consume the JWT for protected routes yet.
- No CORS middleware configured yet — the frontend (Vite, `http://localhost:5173`) will need it once the app is wired up.

## Config / secrets

- `core/config.py`'s `Settings.database_url` and `Settings.secret_key` have **no defaults** — they're required and must come from `backend/.env` (local) or the `DATABASE_URL`/`SECRET_KEY` environment variables (Docker Compose). Previously both had hardcoded fallbacks baked into source (including a real-looking secret key); a missing/misconfigured `.env` now fails loudly at startup instead of silently running with an insecure default.
- `backend/.env` is populated locally and gitignored — don't commit it. There was no `backend/.dockerignore`, so `.env` (and the real `SECRET_KEY`) would get baked into the built image via the Dockerfile's `COPY . .`; added `backend/.dockerignore` to exclude it.
- `docker-compose.yml`'s `backend` service used to inject `SPRING_DATASOURCE_URL`/`SPRING_DATASOURCE_USERNAME`/`SPRING_DATASOURCE_PASSWORD` — dead leftovers from an earlier Spring Boot plan (see `context/plano-infra-docker-kolia-completo.md`). Replaced with `DATABASE_URL` (built from `POSTGRES_*`, same pattern as the `ia-service` block) and `SECRET_KEY: ${JWT_SECRET}`, sourced from the root `.env`'s `JWT_SECRET` — required now that `config.py` has no fallback.
- `requirements.txt` had no version pins; pinned `passlib[bcrypt]==1.7.4` + `bcrypt==4.0.1` because `bcrypt>=4.1` dropped the `__about__.__version__` attribute that `passlib` 1.7.4 (its last release) reads to detect the backend — a widely-hit break for this exact combination.

## Running locally

```bash
cd backend
pip install -r requirements.txt
uvicorn routers.auth:app --reload   # until main.py exists
```

Via Docker Compose (from repo root, once the `main.py` gap above is fixed):

```bash
docker compose up -d --build backend
```

Postgres runs as the `postgres` service in `docker-compose.yml` (image `pgvector/pgvector:pg16`, host port `5433`, container port `5432`).

## Sibling services (context, not owned by this folder)

- `frontend/` — Vite app, expects the backend at `http://localhost:8080`.
- `ia/` — separate FastAPI service (analysis/embeddings via Ollama), has its own `main.py` and README. Per the infra plan, the backend is meant to be the only service the frontend talks to, and the backend calls the IA service — that integration doesn't exist yet in this backend.
