# Async Resumable Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long meeting analyses return immediately, run one at a time, preserve completed chunks, resume interrupted work, and publish the dashboard before embeddings.

**Architecture:** `POST /analisar` prepares and persists every chunk, queues the analysis, and returns HTTP 202. A single in-process worker owns Ollama generation on the reference VPS, resumes missing summaries or embeddings, and uses configurable finite timeouts.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, PostgreSQL/pgvector, HTTPX, Ollama, pytest, Docker Compose.

## Global Constraints

- Input is diarized text; audio transcription is out of scope.
- Reference environment: 2 vCPU, 8 GB RAM, 100 GB NVMe.
- Generation concurrency defaults to exactly `1`.
- Dashboard analysis is readable before embeddings.
- Completed chunks are not repeated after interruption.
- Timeouts remain finite and configurable.
- Do not edit or commit the user's untracked `ia/tests/test_analisar.py`.

---

## File structure

- `ia/src/app/core/config.py`: timeout, retry, and concurrency settings.
- `ia/src/app/services/llm_service.py`: finite HTTP timeout and read-timeout retry.
- `ia/src/app/services/analysis_service.py`: prepare, checkpoint, and resume phases.
- `ia/src/app/services/analysis_worker.py`: serialized background queue.
- `ia/src/app/main.py`: worker lifecycle and asynchronous endpoint.
- `ia/src/app/schemas/analysis.py`: accepted and polling responses.
- `ia/tests/`: behavior tests for each boundary.
- `.env.example`, `docker-compose.yml`, `README.md`: operator configuration.

### Task 1: Configurable finite Ollama timeout

**Files:**
- Modify: `ia/src/app/core/config.py`
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/tests/test_llm_service.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `settings.ollama_generate_timeout_seconds: float`
- Produces: `settings.ollama_embedding_timeout_seconds: float`
- Produces: `settings.ollama_read_timeout_retries: int`
- Preserves the public LLM function signatures.

- [ ] **Step 1: Write failing retry tests**

Add a test whose HTTPX transport raises `httpx.ReadTimeout` once and returns
valid JSON on the next request. Assert two attempts and a decoded response.
Add another test that exhausts the retry and asserts `OllamaError` contains
`timed out`. Assert embeddings receive their separate timeout.

```python
def test_generation_retries_one_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "ollama_read_timeout_retries", 1)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"response": '{"resumo_chunk":"ok"}'})

    result = generate_chunk_summary("conteúdo", client=client_for(handler))
    assert result["resumo_chunk"] == "ok"
    assert attempts == 2
```

- [ ] **Step 2: Verify RED**

Run `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_llm_service.py`.
Expected: FAIL because settings and retry behavior do not exist.

- [ ] **Step 3: Implement the policy**

Add defaults of 600 seconds for generation, 120 seconds for embeddings, one
read-timeout retry, and worker concurrency `1`. Retry only
`httpx.ReadTimeout`; do not retry invalid JSON, model-not-found, or HTTP status
errors. Propagate the four settings through `.env.example` and Compose.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ia/src/app/core/config.py ia/src/app/services/llm_service.py ia/tests/test_llm_service.py .env.example docker-compose.yml
git commit -m "fix: make Ollama timeout policy resilient"
```

### Task 2: Persist preparation and resume summaries

**Files:**
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/tests/test_analysis_service.py`

**Interfaces:**
- Produces: `prepare_analysis(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis`
- Produces: `process_analysis_summaries(db: Session, analysis_id: UUID) -> MeetingAnalysis`

- [ ] **Step 1: Write failing checkpoint tests**

Assert `prepare_analysis` persists every chunk without calling Ollama. Create a
fixture with chunk 1 summarized and chunk 2 empty; assert resume calls the
model only for chunk 2, commits it immediately, consolidates, and reaches
`DASHBOARD_READY`.

```python
def test_resume_skips_completed_chunk(monkeypatch, resumable_session):
    calls = []
    monkeypatch.setattr(
        analysis_service,
        "generate_chunk_summary",
        lambda text: calls.append(text) or complete_summary(text),
    )
    result = analysis_service.process_analysis_summaries(
        resumable_session, ANALYSIS_ID
    )
    assert calls == ["chunk dois"]
    assert result.status == "DASHBOARD_READY"
```

- [ ] **Step 2: Verify RED**

Run `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_analysis_service.py`.
Expected: FAIL because the phase functions do not exist.

- [ ] **Step 3: Implement checkpoint processing**

Preparation sanitizes and splits, creates the analysis and every
`MeetingChunk` with empty summary/vector, then commits. Summary processing sets
`ANALYZING`, skips completed chunks, commits each new summary, consolidates,
sets `DASHBOARD_READY`, and never creates embeddings. On failure, preserve
completed chunks and set `FAILED_ANALYSIS` with the error.

- [ ] **Step 4: Verify GREEN**

Run the Task 2 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ia/src/app/services/analysis_service.py ia/tests/test_analysis_service.py
git commit -m "feat: checkpoint resumable meeting summaries"
```

### Task 3: Resume deferred embeddings

**Files:**
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/tests/test_analysis_service.py`

**Interfaces:**
- Produces: `process_analysis_embeddings(db: Session, analysis_id: UUID) -> MeetingAnalysis`
- Consumes an analysis with a persisted final summary.

- [ ] **Step 1: Write failing embedding tests**

Given chunk 1 with a vector and chunk 2 without one, assert only chunk 2 is
embedded, each vector is committed, and state changes `EMBEDDING` → `DONE`.
On failure, assert `DASHBOARD_READY_WITH_EMBEDDING_ERROR` while the final
summary stays available.

- [ ] **Step 2: Verify RED**

Run the Task 2 test command. Expected: FAIL because the embedding phase is not
independently callable.

- [ ] **Step 3: Implement the embedding phase**

Skip existing vectors, commit each missing vector, set `DONE` when complete,
and preserve dashboard data on failure. Reject execution if no final summary
exists.

- [ ] **Step 4: Verify GREEN**

Run the Task 2 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ia/src/app/services/analysis_service.py ia/tests/test_analysis_service.py
git commit -m "feat: defer and resume meeting embeddings"
```

### Task 4: Serialized background worker

**Files:**
- Create: `ia/src/app/services/analysis_worker.py`
- Create: `ia/tests/test_analysis_worker.py`
- Modify: `ia/src/app/main.py`

**Interfaces:**
- Produces: `AnalysisWorker(session_factory, concurrency: int)`
- Produces: `start()`, `submit(analysis_id)`, and `stop()`.
- Consumes the summary and embedding phase functions.

- [ ] **Step 1: Write failing serialization tests**

Use threading events in two fake jobs. With concurrency `1`, assert job 2
cannot enter before job 1 exits. Assert duplicate IDs are coalesced and one
failed job does not kill the worker.

- [ ] **Step 2: Verify RED**

Run `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_analysis_worker.py`.
Expected: FAIL because `AnalysisWorker` does not exist.

- [ ] **Step 3: Implement worker and recovery**

Use `queue.Queue`, daemon threads, one database session per job, and a locked
set of queued IDs. A job runs summaries, then embeddings. Startup scans and
submits persisted analyses in `PROCESSING`, `ANALYZING`, `DASHBOARD_READY`,
`EMBEDDING`, `FAILED_ANALYSIS`, or
`DASHBOARD_READY_WITH_EMBEDDING_ERROR`. Shutdown drains no new work and joins
threads with a bounded wait.

- [ ] **Step 4: Verify GREEN**

Run the Task 4 test command. Expected: serialization, coalescing, failure
isolation, and clean shutdown pass.

- [ ] **Step 5: Commit**

```bash
git add ia/src/app/services/analysis_worker.py ia/tests/test_analysis_worker.py ia/src/app/main.py
git commit -m "feat: serialize background meeting analysis"
```

### Task 5: HTTP 202 and polling contract

**Files:**
- Modify: `ia/src/app/schemas/analysis.py`
- Modify: `ia/src/app/main.py`
- Modify: `ia/tests/test_api.py`
- Modify: `README.md`

**Interfaces:**
- `POST /analisar` returns HTTP 202 after persistence.
- `GET /analises/{analysis_id}` exposes current state and available summary.

- [ ] **Step 1: Write failing API tests**

Override database and worker dependencies. Assert POST calls preparation and
`worker.submit(id)` once, returns 202 without inference, and GET exposes a
summary in both dashboard-ready states.

- [ ] **Step 2: Verify RED**

Run `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_api.py`.
Expected: FAIL because POST blocks and returns 200.

- [ ] **Step 3: Implement accepted-and-poll behavior**

POST prepares, queues, and returns immediately with `final_summary=None`.
Document polling until `DASHBOARD_READY`, `DONE`, `FAILED_ANALYSIS`, or
`DASHBOARD_READY_WITH_EMBEDDING_ERROR`. Do not fabricate a progress percentage.

- [ ] **Step 4: Verify GREEN**

Run the Task 5 test command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ia/src/app/schemas/analysis.py ia/src/app/main.py ia/tests/test_api.py README.md
git commit -m "feat: accept and poll long meeting analyses"
```

### Task 6: Full verification and transcript benchmark

**Files:**
- Modify only if recording measured results: `README.md`
- Do not modify: `ia/tests/test_analisar.py`

**Interfaces:**
- Validates the complete contract from Tasks 1–5.

- [ ] **Step 1: Run all automated tests**

Run `docker compose run --rm --no-deps ia-service python -m pytest -q tests`.
Expected: all tests pass without warnings or tracebacks.

- [ ] **Step 2: Rebuild and health-check**

Run `docker compose up -d --build ia-service`, then
`docker compose ps ia-service ollama postgres`, then
`curl --fail http://localhost:3000/health`.
Expected: services running and health status `ok`.

- [ ] **Step 3: Run the existing transcript test once**

Run `python ia/tests/test_analisar.py`.
Expected: POST quickly returns HTTP 202 plus `analysis_id`.

- [ ] **Step 4: Poll by condition**

Poll `GET /analises/{analysis_id}` every five seconds and stop at a terminal or
dashboard-ready state. Inspect `/analises/{analysis_id}/chunks` and verify
completed summaries remain persisted.

- [ ] **Step 5: Verify resources and serialization**

Run `docker stats --no-stream dashboard-kolia-ollama-1 dashboard-kolia-ia-service-1`
and `docker compose logs --since=30m ia-service ollama`.
Expected: no overlapping KOLIA generation jobs, no 180-second timeout, and
memory within the 8 GB target.

- [ ] **Step 6: Commit benchmark documentation only if changed**

```bash
git add README.md
git commit -m "docs: record async analysis benchmark"
```

Skip this commit when README is unchanged.

## Follow-up plan

After this stability plan passes, create a separate plan for factual and
commercial prompts, satisfaction estimated by AI, detailed timings, aggregate
dashboard APIs, and replacement of frontend mocks. Those features depend on
the reliable checkpoints delivered here.
