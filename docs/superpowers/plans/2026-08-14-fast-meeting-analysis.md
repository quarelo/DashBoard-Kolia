# Fast Meeting Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Minimize complete analysis time for a roughly 40,000-token meeting, targeting a warm run of at most five minutes on 2 vCPU and 8 GB RAM without losing critical facts.

**Architecture:** Deterministically compact speaker turns before token splitting, summarize chunks with a separately configurable small model and short output budget, consolidate with the quality model, and optionally process two chunks concurrently only when benchmark evidence supports it. Preserve per-chunk checkpoints and repair malformed JSON once.

**Tech Stack:** Python 3.11, FastAPI, Pydantic Settings, SQLAlchemy, HTTPX, Ollama, pytest, Docker Compose.

## Global Constraints

- Preserve decisions, commitments, owners, values, quantities, deadlines, questions, negations, evidence, and explicit actions.
- Never invent actions or facts.
- Embeddings remain outside the measured dashboard critical path.
- Chunk concurrency is limited to `1` or `2`; default selection is based on benchmark evidence.
- Do not modify or commit the user's untracked `ia/tests/test_analisar.py`.
- Do not create commits unless the user later requests them.

---

### Task 1: Turn-aware deterministic compaction

**Files:**
- Modify: `ia/src/app/services/chunk_service.py`
- Modify: `ia/tests/test_chunk_service.py`

**Interfaces:**
- Produces: `clean_transcription(text: str) -> str`
- Preserves: `sanitize_transcription(text: str) -> str`
- Preserves: `clean_chunk_text(text: str) -> str`

- [ ] **Step 1: Write failing tests**

Add tests proving that consecutive `[LOCUTOR N]` fragments merge into `[LN]:`, entire small-talk turns disappear, duplicate turns disappear, and turns containing numbers, questions, negations, deadlines, or substantive text remain.

```python
def test_clean_transcription_compacts_and_merges_speaker_turns():
    text = "[LOCUTOR 12]: Boa tarde. [LOCUTOR 7]: A entrega é dia 20. [LOCUTOR 7]: Não pode atrasar."
    assert clean_transcription(text) == "[L7]: A entrega é dia 20. Não pode atrasar."

def test_clean_transcription_preserves_questions_and_numbers():
    text = "[LOCUTOR 2]: Tudo bem? [LOCUTOR 3]: O valor não será R$ 500?"
    assert "O valor não será R$ 500?" in clean_transcription(text)
```

- [ ] **Step 2: Verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_chunk_service.py`
Expected: FAIL because `clean_transcription` does not exist.

- [ ] **Step 3: Implement compaction**

Parse speaker markers with a compiled regex, normalize each turn, classify small-talk only when the whole turn is non-substantive, merge adjacent turns by speaker, and deduplicate exact normalized turns. Make `clean_chunk_text` delegate to the safe cleaning primitives without deleting phrases inside substantive turns.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 command. Expected: all tests pass.

---

### Task 2: Efficient splitting and separate model configuration

**Files:**
- Modify: `ia/src/app/core/config.py`
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/tests/test_analysis_service.py`
- Modify: `ia/tests/test_llm_service.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces settings: `chunk_model: str`, `consolidation_model: str`, `chunk_processing_concurrency: int`, `ollama_keep_alive: str`
- `generate_chunk_summary` consumes `settings.chunk_model`.
- `consolidate_summaries` consumes `settings.consolidation_model`.

- [ ] **Step 1: Write failing configuration and preparation tests**

Assert chunk generation and consolidation send different configured models and `keep_alive`; assert preparation splits the cleaned transcription, records original token count, and stores compacted chunk content with zero overlap under optimized defaults.

```python
def test_chunk_and_consolidation_use_separate_models(monkeypatch):
    monkeypatch.setattr(settings, "chunk_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "consolidation_model", "qwen2.5:3b")
    # Mock transports assert each payload model and keep_alive.
```

- [ ] **Step 2: Verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_llm_service.py tests/test_analysis_service.py`
Expected: FAIL because separate settings and cleaned preparation are absent.

- [ ] **Step 3: Implement minimal configuration**

Set optimized defaults: chunk model `qwen2.5:1.5b`, consolidation model `qwen2.5:3b`, chunk thinking `false`, consolidation thinking `false`, chunk output `384`, consolidation output `768`, overlap `0`, concurrency `1`, and keep-alive `30m`. Keep `MODEL` as a backward-compatible fallback when explicit model settings are absent.

In `prepare_analysis`, calculate `total_tokens` from sanitized original input, call `clean_transcription`, split the compacted result, and persist the cleaned content.

- [ ] **Step 4: Verify GREEN**

Run the Task 2 command. Expected: all tests pass.

---

### Task 3: Bounded malformed-JSON recovery

**Files:**
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/tests/test_llm_service.py`

**Interfaces:**
- Produces: `_extract_json_object(raw: str) -> dict[str, Any] | None`
- Produces: `_repair_json(raw: str, schema: dict[str, Any], *, client: httpx.Client | None) -> dict[str, Any]`
- `_generate_json` makes at most one repair request when enabled.

- [ ] **Step 1: Write failing recovery tests**

Test fenced JSON, surrounding prose, truncated-invalid JSON followed by a valid repair response, and a failed repair. Assert only one repair request and ensure raised errors include a bounded diagnostic rather than the prompt/transcription.

```python
def test_generation_repairs_invalid_json_once(monkeypatch):
    responses = iter(["{invalid", json.dumps({"resumo_chunk": "ok"})])
    # Assert two calls and a decoded object.
```

- [ ] **Step 2: Verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_llm_service.py`
Expected: FAIL because extraction and repair do not exist.

- [ ] **Step 3: Implement bounded recovery**

First parse directly, then strip a Markdown fence or extract the first balanced JSON object. If still invalid and repair is enabled, submit only the bounded raw response plus schema using the chunk model, `think=false`, and a short output budget. Validate that the result is an object. Log only response length and a truncated escaped prefix.

- [ ] **Step 4: Verify GREEN**

Run the Task 3 command. Expected: all tests pass.

---

### Task 4: Checkpoint-safe chunk concurrency

**Files:**
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/tests/test_analysis_service.py`

**Interfaces:**
- Produces: `_generate_pending_summaries(chunks: list[MeetingChunk], concurrency: int) -> dict[int, dict]`
- `process_analysis_summaries` persists generated summaries in ascending chunk order.

- [ ] **Step 1: Write failing concurrency tests**

Use events and a thread-safe call recorder to prove concurrency `2` overlaps two independent generation calls, concurrency `1` remains serial, completed chunks are skipped, results attach to the correct indices, and a failure leaves prior committed checkpoints reusable.

- [ ] **Step 2: Verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_analysis_service.py`
Expected: FAIL because pending summary generation is serial.

- [ ] **Step 3: Implement bounded executor**

Validate concurrency is `1` or `2`. Use `ThreadPoolExecutor` only for missing summaries. Do not share SQLAlchemy sessions with threads: threads call Ollama and return values; the owning worker thread assigns results and commits each chunk in original index order. Cancel unstarted futures after a failure and preserve all already committed results.

- [ ] **Step 4: Verify GREEN**

Run the Task 4 command. Expected: all tests pass.

---

### Task 5: Benchmark instrumentation and comparison

**Files:**
- Create: `ia/scripts/benchmark_analysis.py`
- Create: `ia/tests/test_benchmark_analysis.py`
- Modify: `README.md`

**Interfaces:**
- Produces CLI options: `--input`, `--meeting-id`, `--variants`, `--output`
- Produces a JSON report containing variant configuration, original/clean token counts, reduction ratio, chunks, preparation seconds, chunk seconds, consolidation seconds, total critical-path seconds, peak RSS, errors, and required-field coverage.

- [ ] **Step 1: Write failing report tests**

Mock analysis execution and resource sampling. Assert stable JSON keys, correct reduction and elapsed calculations, and failure reporting without aborting later variants.

- [ ] **Step 2: Verify RED**

Run: `docker compose run --rm --no-deps ia-service python -m pytest -q tests/test_benchmark_analysis.py`
Expected: FAIL because the benchmark module does not exist.

- [ ] **Step 3: Implement benchmark CLI**

Implement four named variants: `baseline-3b`, `optimized-3b`, `hybrid-1.5b-3b`, and `hybrid-parallel-2`. Preload required Ollama models with an empty prompt and configured keep-alive. Measure only preparation through final consolidation for the critical path; record embeddings separately if requested. Use the existing HTTP service or service functions without duplicating analysis logic.

- [ ] **Step 4: Verify GREEN and full regression**

Run:

```bash
docker compose run --rm --no-deps ia-service python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Run the controlled benchmark**

Run the four variants against the transcription from `ia/tests/test_analisar.py`, without editing that file. Confirm required models exist before running. Save the report under `ia/logs/benchmark-2026-08-14.json`.

Acceptance: select the fastest variant that preserves every required field and critical reference fact, remains within available RAM, and does not use excessive swap. Prefer concurrency `1` unless concurrency `2` measurably reduces total time. Report whether the warm critical path meets 300 seconds and identify the measured bottleneck otherwise.

---

### Task 6: Relevance retention and missing-field completion

**Files:**
- Modify: `ia/src/app/services/chunk_service.py`
- Modify: `ia/src/app/services/analysis_service.py`
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `ia/src/app/core/config.py`
- Modify: `ia/scripts/benchmark_analysis.py`
- Modify: focused tests for each service

- [ ] Write failing tests for chronological relevance selection at 15%, 25%, and 35%.
- [ ] Implement scoring that prioritizes decisions, actions, dates, values, questions, and negations.
- [ ] Write failing tests proving only empty final fields are requested and existing fields are preserved.
- [ ] Implement one bounded missing-field completion call.
- [ ] Add benchmark variants for the three retention ratios.
- [ ] Run focused tests, full regression, and timed real benchmarks.
