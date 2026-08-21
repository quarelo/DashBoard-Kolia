# Analysis Progress API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose useful, accurate progress metadata while the meeting summary is generated progressively.

**Architecture:** Derive progress from persisted chunk summaries so restarts remain accurate. A focused service function calculates completed chunks, percentage, partial state, and remaining-time estimate; existing API response builders attach those values without changing current fields.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, pytest.

## Global Constraints

- Preserve all existing API response fields.
- Read and eventually summarize 100% of the cleaned transcription.
- Expose a partial summary as soon as the first chunk completes.
- Do not commit changes.

---

### Task 1: Progress calculation

**Files:**
- Modify: `ia/src/app/services/analysis_service.py`
- Test: `ia/tests/test_analysis_service.py`

**Interfaces:**
- Consumes: `MeetingAnalysis`, ordered `MeetingChunk` values, current time.
- Produces: `build_analysis_progress(analysis, chunks, now=None) -> dict` containing `processed_chunks`, `total_chunks`, `progress_percent`, `is_partial`, and `estimated_seconds_remaining`.

- [ ] Write failing tests for zero progress, partial progress, completed progress, and a non-negative estimate.
- [ ] Run the focused tests and verify the missing function causes failure.
- [ ] Implement persisted-state calculation, returning `None` for the estimate until timing data exists.
- [ ] Run focused tests and verify they pass.

### Task 2: API response fields

**Files:**
- Modify: `ia/src/app/schemas/analysis.py`
- Modify: `ia/src/app/main.py`
- Test: `ia/tests/test_main.py`

**Interfaces:**
- Consumes: `build_analysis_progress` and database chunks.
- Produces: the five progress fields on POST and both GET detail endpoints.

- [ ] Write a failing API test asserting progress fields for an analysis with summarized chunks.
- [ ] Run the focused test and verify fields are absent.
- [ ] Extend schemas and response builders with backward-compatible fields.
- [ ] Run focused tests and verify they pass.

### Task 3: Verification

**Files:**
- Verify: all files above.

**Interfaces:**
- Consumes: implemented progress API.
- Produces: rebuilt, running service with passing tests.

- [ ] Run the complete IA test suite.
- [ ] Rebuild `ia-service` and confirm effective model/chunk configuration.
- [ ] Exercise a read endpoint and inspect the JSON contract.
