# Progressive Analysis Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deterministic preliminary result in 30 seconds, a distributed partial result in 5 minutes, and a complete summary in 12 minutes on the production VPS while still reading 100% of the cleaned transcription.

**Architecture:** Persist a preliminary full-transcript extraction immediately, prioritize a chronologically distributed set of high-signal chunks, reuse those checkpoints in the complete pass, and separate summary progress from embeddings. Benchmark 16-, 20-, and 24-chunk variants on the fixed worst-case transcription and keep the fastest quality-passing configuration.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL/pgvector, Ollama, pytest, Docker Compose.

## Global Constraints

- Keep inference local; do not add external APIs or GPU requirements.
- Preserve 100% full-summary coverage of the cleaned transcription.
- Preliminary target: at most 30 seconds.
- Distributed partial target: at most 5 minutes.
- Complete-summary target on the final VPS: at most 12 minutes.
- Embeddings remain outside the summary critical path.
- Peak combined memory target: below 6 GiB.
- Do not modify `ia/tests/test_analisar.py`.
- Do not create commits.

---

### Task 1: Persist summary stages and independent progress

**Files:**
- Modify: `ia/src/app/models/analysis.py`
- Modify: `ia/src/app/core/database.py`
- Modify: `ia/src/app/schemas/analysis.py`
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/tests/test_analysis_service.py`
- Modify: `ia/tests/test_api.py`

**Interfaces:**
- Produces: `summary_stage`, `summary_is_final`, `summary_progress_percent`, `embedding_progress_percent`, and `summary_estimated_seconds_remaining` on analysis responses.
- Preserves: `progress_percent` and `estimated_seconds_remaining` as summary-progress aliases.

- [ ] Write failing tests proving a new analysis is `PRELIMINARY`, a finished summary is `COMPLETE` while embeddings may still run, and embedding progress counts persisted vectors independently.
- [ ] Run the focused tests and verify the fields/derivation are missing.
- [ ] Add compatible database columns with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and mapped defaults.
- [ ] Extend response schemas and `build_analysis_progress` without removing current fields.
- [ ] Run focused tests and the complete suite.

### Task 2: Build a full-transcript preliminary summary

**Files:**
- Create: `ia/src/app/services/preliminary_summary_service.py`
- Create: `ia/tests/test_preliminary_summary_service.py`
- Modify: `ia/src/app/services/analysis_service.py`

**Interfaces:**
- Produces: `build_preliminary_summary(cleaned_transcription: str) -> dict`.
- Output: the existing nine final-summary keys, populated only from explicitly matched text.

- [ ] Write failing tests with facts from the worst-case fixture: `CRM para 25 pessoas`, the 20/40-license discussion, Monday plans, 27 machines, and March/April cloud study.
- [ ] Verify RED because the service does not exist.
- [ ] Implement bounded deterministic extraction for quantities, monetary values, dates, commitments, questions, and negations; retain source wording and deduplicate.
- [ ] Persist this result during `prepare_analysis`, set `summary_stage=PRELIMINARY`, and commit before queue submission.
- [ ] Verify focused tests, API tests, and the complete suite.

### Task 3: Prioritize distributed relevant chunks

**Files:**
- Modify: `ia/src/app/services/chunk_service.py`
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/tests/test_chunk_service.py`
- Modify: `ia/tests/test_analysis_service.py`

**Interfaces:**
- Produces: `rank_chunk_indices_for_partial(chunks, limit) -> list[int]`.
- Ordering: priority subset first, remaining indices in original chronological order.

- [ ] Write failing tests proving selection includes beginning, middle, and end and prioritizes decisions, actions, dates, values, questions, and negations.
- [ ] Verify RED against the current chronological-only scheduler.
- [ ] Implement deterministic scoring plus chronological bucket coverage; cap the priority subset to the configured partial-chunk count.
- [ ] Change pending-summary scheduling to run priority indices first and reuse their persisted summaries in the complete pass.
- [ ] Set `summary_stage=PARTIAL` after the first priority checkpoint and rebuild the partial summary after each checkpoint.
- [ ] Verify restart behavior, no duplicate generation, focused tests, and the full suite.

### Task 4: Instrument retries and effective prompt limits

**Files:**
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/scripts/benchmark_analysis.py`
- Modify: `ia/tests/test_llm_service.py`
- Modify: `ia/tests/test_benchmark_analysis.py`

**Interfaces:**
- Produces per-run metrics: generation attempts, truncation retries, effective input size, time to first/partial/complete result, and embedding time.

- [ ] Write failing tests for retry counters, stage timestamps, and explicit prompt-truncation failure reporting.
- [ ] Verify RED.
- [ ] Add bounded metric collection without logging transcription contents.
- [ ] Include stage timings and retry totals in benchmark JSON.
- [ ] Reject benchmark variants when Ollama reports input truncation or required reference facts are absent.
- [ ] Run focused and full tests.

### Task 5: Benchmark 16, 20, and 24 chunks

**Files:**
- Modify: `ia/scripts/benchmark_analysis.py`
- Modify: `ia/tests/test_benchmark_analysis.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces variants `full-16`, `full-20`, `full-24`, with concurrency `1` and `2` where safe.
- Produces report under `ia/logs/` with stage times, quality gates, retries, CPU, and memory.

- [ ] Write failing tests for variant configuration and acceptance-gate reporting.
- [ ] Verify RED.
- [ ] Add exact chunk-size variants derived from the cleaned 40,008-token fixture and configurable partial subset size.
- [ ] Run each variant against `ia/tests/test_analisar.py` without modifying it.
- [ ] Select the fastest variant that has zero prompt truncations and retains all five reference-fact groups.
- [ ] Rebuild `ia-service`, execute a fresh endpoint run to `DONE`, run all tests, and report full JSON, stage times, retries, CPU, peak memory, and whether each SLA was met.
