# RAG Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose isolated semantic retrieval with source evidence over completed meeting embeddings, ready for a future chatbot without adding generation or chat history now.

**Architecture:** Embed a bounded query with the existing Ollama embedding model, rank only chunks belonging to the requested analysis by pgvector cosine distance, and return cleaned excerpts plus similarity metadata. Retrieval remains unavailable until all embeddings for that analysis are ready and never enters the summary critical path.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/pgvector, Ollama, pytest.

## Global Constraints

- Do not add chatbot generation, conversation history, or UI.
- Do not run retrieval before embeddings are complete.
- Never retrieve chunks from another analysis.
- Bound `top_k` to 1 through 10, default 5.
- Return evidence excerpts and stable relevance ordering.
- Do not modify `ia/tests/test_analisar.py`.
- Do not create commits.

---

### Task 1: Retrieval service

**Files:**
- Create: `ia/src/app/services/retrieval_service.py`
- Create: `ia/tests/test_retrieval_service.py`

**Interfaces:**
- Produces: `retrieve_analysis_chunks(db, analysis, query, top_k) -> list[RetrievedChunk]`.
- Consumes: existing `generate_embedding(query)` and `MeetingChunk.embedding.cosine_distance(query_vector)`.

- [ ] Write failing tests for readiness rejection, analysis-ID isolation, cosine ordering, `top_k`, and missing/empty queries.
- [ ] Verify RED because the service does not exist.
- [ ] Implement validation: only `DONE` analyses with every chunk embedding present are searchable.
- [ ] Build one SQL statement filtered by `MeetingChunk.analysis_id`, non-null embedding, ordered by cosine distance and chunk index as stable tie-breaker, limited by `top_k`.
- [ ] Convert distance to bounded similarity `1 - distance` and return cleaned content with chunk identity.
- [ ] Run focused tests and verify GREEN.

### Task 2: Retrieval API contract

**Files:**
- Modify: `ia/src/app/schemas/analysis.py`
- Modify: `ia/src/app/main.py`
- Modify: `ia/tests/test_api.py`

**Interfaces:**
- Produces: `POST /analises/{analysis_id}/buscar`.
- Request: `{ "query": string, "top_k": integer = 5 }`.
- Response: `{ "analysis_id", "query", "results": [{ "chunk_id", "chunk_index", "content", "similarity" }] }`.

- [ ] Write failing API tests for 404 analysis, 409 embeddings-not-ready, 422 invalid query/top_k, and successful evidence ordering.
- [ ] Verify RED because the route and schemas are missing.
- [ ] Add bounded Pydantic request/response schemas.
- [ ] Add the route and map retrieval readiness to HTTP 409 without exposing internal errors.
- [ ] Run API tests and the full suite.

### Task 3: Real worst-case retrieval verification

**Files:**
- Modify: `README.md`
- Verify: existing completed giant analysis and all RAG files.

**Interfaces:**
- Consumes: a `DONE` 48-chunk analysis with embeddings.
- Produces: measured evidence results for reference queries.

- [ ] Rebuild `ia-service` and confirm database/vector readiness.
- [ ] Query the completed giant analysis for licenses, Monday plans, 27 machines, and March/April cloud study.
- [ ] Verify every result belongs to the requested analysis and contains the supporting excerpt.
- [ ] Measure query latency and memory without invoking the generative model.
- [ ] Run the complete automated suite and report query JSON, latency, CPU, memory, and any missed reference query.
