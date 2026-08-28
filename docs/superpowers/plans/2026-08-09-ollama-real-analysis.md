# Ollama Real Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace deterministic mock summaries and embeddings with real Ollama calls configured by environment variables.

**Architecture:** A focused Ollama client in `llm_service.py` owns HTTP payloads, JSON parsing, model errors, and embedding dimension validation. `analysis_service.py` orchestrates those calls and keeps the existing database/API contract. The interactive installer owns model availability and `.env` updates; the API never downloads models.

**Tech Stack:** Python 3.11, FastAPI, HTTPX, Pydantic, Ollama HTTP API, pytest, Docker Compose, PostgreSQL/pgvector.

## Global Constraints

- The generation model comes from `OLLAMA_MODEL` through Compose `MODEL` and `settings.model`.
- The embedding model comes from `EMBEDDING_MODEL` and `settings.embedding_model`.
- Missing models produce a clear `FAILED` analysis with guidance to run `./ia/install-model.sh`.
- No silent fallback to mock summaries or embeddings.
- Do not create commits.

---

### Task 1: Real Ollama client

**Files:**
- Modify: `ia/tests/test_llm_service.py`
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/src/app/core/config.py`

**Interfaces:**
- Produces: `generate_chunk_summary(clean_content: str) -> dict`
- Produces: `consolidate_summaries(chunk_summaries: list[dict]) -> dict`
- Produces: `generate_embedding(text: str) -> list[float]`

- [ ] **Step 1: Write failing HTTP-boundary tests**

Add tests using `httpx.MockTransport` that assert the configured model is sent to `/api/generate`, JSON from `response` is decoded, the configured embedding model is sent to `/api/embed`, invalid JSON raises `OllamaResponseError`, missing model responses mention `./ia/install-model.sh`, and vectors with a dimension different from `settings.embedding_dim` are rejected.

- [ ] **Step 2: Run tests to verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_llm_service.py`

Expected: FAIL because the real client functions and errors do not exist.

- [ ] **Step 3: Implement minimal real client**

Use `httpx.Client` with injectable transport/client, POST generation payloads containing `model=settings.model`, `stream=False`, `format="json"`, `temperature=0`; decode `data["response"]` with `json.loads`. POST embeddings with `model=settings.embedding_model` and `input=text`; return `data["embeddings"][0]` only when its size equals `settings.embedding_dim`. Translate 404/model-not-found responses to an error that tells the operator to run `./ia/install-model.sh`.

- [ ] **Step 4: Run focused and complete tests**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_llm_service.py tests`

Expected: all tests pass with no warnings.

### Task 2: Wire real calls into analysis processing

**Files:**
- Modify: `ia/tests/test_api.py`
- Modify: `ia/src/app/services/analysis_service.py`

**Interfaces:**
- Consumes: the three real client functions from Task 1.
- Preserves: `analyze_meeting(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis`.

- [ ] **Step 1: Write a failing orchestration test**

Test the analysis service with controlled real-client boundaries and assert it persists the returned chunk summary, embedding, and final consolidation, with no reference to any `*_mock_*` function.

- [ ] **Step 2: Run test to verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_api.py`

Expected: FAIL because orchestration still imports mock functions.

- [ ] **Step 3: Replace mock orchestration calls**

Import and call `generate_chunk_summary`, `generate_embedding`, and `consolidate_summaries`. Preserve transaction handling so any Ollama error marks the analysis `FAILED` and records the useful message.

- [ ] **Step 4: Run the complete suite**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests`

Expected: all tests pass.

### Task 3: Environment-aware interactive installer

**Files:**
- Modify: `ia/install-model.sh`
- Modify: `ia/.env.example`
- Modify: `ia/README.md`

**Interfaces:**
- Consumes: root `.env` variables `OLLAMA_MODEL` and `EMBEDDING_MODEL`.
- Produces: installed Ollama models or an updated root `.env` after explicit operator choice.

- [ ] **Step 1: Add a shell behavior test**

Add `ia/tests/test_install_model.py` that runs the script against fake `docker` and a temporary env file. Assert an installed model causes no pull, choosing download pulls the configured model, and choosing replacement updates only the requested env key.

- [ ] **Step 2: Run installer tests to verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_install_model.py`

Expected: FAIL because the current script always asks for an arbitrary name and does not read the env.

- [ ] **Step 3: Implement the installer workflow**

Load root `.env` without executing it, use Compose defaults when keys are absent, inspect `ollama list`, and prompt to download, replace, or cancel. Apply the same function to generation and embedding models. Update README with `./ia/install-model.sh` as the recovery command.

- [ ] **Step 4: Run installer and complete tests**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests`

Expected: all tests pass.

### Task 4: Real-container validation

**Files:**
- Modify only if validation exposes a tested defect.

- [ ] **Step 1: Ensure configured models exist**

Run `./ia/install-model.sh` interactively. If the environment-selected models are missing, use the approved installer choice rather than changing code defaults.

- [ ] **Step 2: Rebuild and start IA**

Run: `docker compose up -d --build ia-service`

- [ ] **Step 3: Exercise real analysis**

POST a representative Portuguese meeting to `/analisar`, then GET the analysis and chunks. Assert status is `DONE`, the final summary is model-produced rather than the old mock sentence, and the stored embedding has `EMBEDDING_DIM` dimensions.

- [ ] **Step 4: Fresh completion verification**

Run the complete pytest suite, `docker compose ps`, inspect IA logs, query pgvector dimensions, and run `git diff --check`. All must complete without errors.
