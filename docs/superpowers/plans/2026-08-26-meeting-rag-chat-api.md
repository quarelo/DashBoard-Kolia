# Meeting RAG Chat API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fast, grounded `POST /analises/{analysis_id}/chat` API with request-provided history, server-owned citations, safe fallbacks, and deterministic regression tests based on the large meeting fixture.

**Architecture:** Extend the existing analysis schemas and RAG retrieval, add a focused chat orchestration service, and expose it through FastAPI. Retrieval remains scoped by `analysis_id`; the model is called once only when evidence passes a similarity threshold, and failures return a safe “not found” response.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy/pgvector, httpx, Ollama, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-meeting-rag-chat-api-design.md`

## Global Constraints

- Do not commit changes.
- Do not rerun the 24-minute giant analysis benchmark.
- Use TDD: observe each new behavior fail before writing production code.
- Keep all retrieval scoped to the requested `analysis_id`.
- Use at most one embedding request and one text-generation request per chat call.
- Return `Não encontrei essa informação na transcrição desta reunião.` whenever evidence or model output cannot safely support an answer.

---

### Task 1: Chat request and response contract

**Files:**
- Modify: `ia/src/app/schemas/analysis.py`
- Test: `ia/tests/test_chat_schemas.py`

**Interfaces:**
- Produces: `ChatHistoryMessage`, `ChatRequest`, `ChatCitation`, and `ChatResponse` Pydantic models.
- `ChatRequest` contains `question: str`, `history: list[ChatHistoryMessage]`, and `top_k: int`.

- [ ] **Step 1: Write failing schema tests** for valid history, invalid role, excessive history, non-alternating roles, history ending in `user`, whitespace-only questions, and `top_k` limits.
- [ ] **Step 2: Run** `pytest -q ia/tests/test_chat_schemas.py` and verify failures are caused by missing chat schemas.
- [ ] **Step 3: Implement minimal Pydantic schemas and model validation** with question length 2–500, message length 1–1000, at most six history messages, alternating roles, and final role `assistant`.
- [ ] **Step 4: Run** `pytest -q ia/tests/test_chat_schemas.py` and verify it passes.

### Task 2: Configurable plain-text Ollama generation

**Files:**
- Modify: `ia/src/app/core/config.py`
- Modify: `ia/src/app/services/llm_service.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Test: `ia/tests/test_llm_service.py`

**Interfaces:**
- Produces: `generate_chat_answer(prompt: str, *, client: httpx.Client | None = None) -> str`.
- Adds settings for `chat_num_predict=512`, `chat_temperature=0.1`, `chat_similarity_threshold`, `chat_max_evidence_chars`, and `chat_generate_timeout_seconds`.

- [ ] **Step 1: Write a failing test** asserting one non-streaming Ollama request, configured model, `think=false`, temperature, 512-token limit, 8192 `num_ctx`, and stripped textual output.
- [ ] **Step 2: Run the focused test** and verify it fails because `generate_chat_answer` is missing.
- [ ] **Step 3: Implement the minimal plain-text generation wrapper** using the existing `_post_json` transport and reject missing/blank `response` fields with `OllamaResponseError`.
- [ ] **Step 4: Run focused and complete LLM tests** with `pytest -q ia/tests/test_llm_service.py`.
- [ ] **Step 5: Document matching environment defaults** and change the effective Compose context from 4096 to `${OLLAMA_CONTEXT_LENGTH:-8192}`.

### Task 3: Grounded chat orchestration and fallbacks

**Files:**
- Create: `ia/src/app/services/chat_service.py`
- Test: `ia/tests/test_chat_service.py`

**Interfaces:**
- Consumes: `search_analysis_chunks(db, analysis_id, query, top_k)` and `generate_chat_answer(prompt)`.
- Produces: `answer_analysis_question(db, analysis_id: UUID, request: ChatRequest) -> dict`.
- Produces: `UNKNOWN_ANSWER`, `INSUFFICIENT_EVIDENCE`, and `MODEL_UNAVAILABLE` stable constants.

- [ ] **Step 1: Write failing tests** for query enrichment from the latest user/assistant pair, strong evidence generation, similarity filtering, no-model-call fallback, model exception fallback, blank response fallback, server-owned citations, prompt injection delimiters, and known meeting facts (25 CRM users, 27 Windows 11 machines, March/April cloud study).
- [ ] **Step 2: Run** `pytest -q ia/tests/test_chat_service.py` and verify the module/function absence causes the failures.
- [ ] **Step 3: Implement query construction** using bounded history plus the current question.
- [ ] **Step 4: Implement evidence filtering and prompt construction** with numbered, bounded, explicitly untrusted transcript excerpts.
- [ ] **Step 5: Implement safe orchestration** that skips generation on weak evidence, catches known `OllamaError` failures, rejects blank output, and attaches citations solely from filtered retrieval results.
- [ ] **Step 6: Run** `pytest -q ia/tests/test_chat_service.py` and verify all cases pass.

### Task 4: FastAPI chat endpoint

**Files:**
- Modify: `ia/src/app/main.py`
- Test: `ia/tests/test_api.py`

**Interfaces:**
- Consumes: `answer_analysis_question(db, analysis_id, payload)`.
- Produces: `POST /analises/{analysis_id}/chat` with `ChatResponse`.

- [ ] **Step 1: Write failing route tests** for grounded success, safe fallback, missing analysis mapped to 404, RAG-not-ready mapped to 409, unexpected infrastructure failure mapped to 503, and invalid payload mapped to 422.
- [ ] **Step 2: Run focused API chat tests** and verify 404/missing-route failures.
- [ ] **Step 3: Implement the endpoint and exact exception mapping** without exposing internal error details.
- [ ] **Step 4: Run** `pytest -q ia/tests/test_api.py` and verify it passes.

### Task 5: Regression and verification

**Files:**
- Modify only files required by failures attributable to the chat implementation.

**Interfaces:**
- Validates all earlier tasks; produces no new API.

- [ ] **Step 1: Run chat-focused tests** with `pytest -q ia/tests/test_chat_schemas.py ia/tests/test_chat_service.py ia/tests/test_api.py ia/tests/test_llm_service.py`.
- [ ] **Step 2: Run the full IA suite** with `docker compose run --rm --no-deps -v "$PWD/ia:/app" ia-service python -m pytest -q` if the local Python environment cannot resolve service dependencies.
- [ ] **Step 3: Run `git diff --check`** and inspect the final diff for accidental changes to the giant fixture or unrelated user work.
- [ ] **Step 4: Report exact test results, configuration defaults, request example, known limitations, and any existing unrelated failures. Do not commit.**
