# Progressive Production Analysis Design

## Goal

Make the local CPU-only meeting analysis useful quickly while preserving a
complete final result for the 40,008-token worst-case transcription.

Measured acceptance targets on the final VPS are:

- preliminary deterministic summary in at most 30 seconds;
- useful partial summary distributed across the meeting in at most 5 minutes;
- final summary covering 100% of the cleaned transcription in at most 12 minutes;
- summary completion must not wait for embeddings;
- peak combined memory must remain below 6 GiB;
- critical reference facts must be retained.

The current development machine is the baseline for comparison, not the final
12-minute acceptance environment. Its latest full run took 1,932.239 seconds:
1,757.757 seconds for 48 summaries and 173.891 seconds for embeddings.

## Recommended Architecture

The analysis exposes three summary stages.

1. `PRELIMINARY`: deterministic extraction scans the full cleaned transcript
   for explicit quantities, dates, commitments, questions, and negations. It
   produces a safe first result without waiting for Ollama.
2. `PARTIAL`: a small relevance-selected set distributed across the full
   meeting is summarized first. The selected segments preserve chronological
   coverage rather than taking only the beginning.
3. `COMPLETE`: every cleaned transcription segment is summarized and merged.
   Previously completed priority segments are reused rather than generated
   again.

Embeddings start only after the complete summary is persisted. They remain a
separate background stage and never delay dashboard availability.

## RAG Foundation

The current pgvector embeddings become the retrieval foundation for a future
chatbot, but conversational generation remains out of scope for this phase.

- Retrieval runs only against persisted embeddings after summary completion.
- A focused service accepts an analysis ID, a query, and a bounded `top_k`.
- The query is embedded with the configured embedding model.
- PostgreSQL cosine distance selects the most relevant chunks from that
  analysis only.
- Results return chunk ID/index, original cleaned excerpt, and similarity
  score so downstream answers can cite evidence.
- Retrieval never changes summary status and never enters the summary critical
  path.
- Requests made before embeddings are ready return an explicit readiness
  response rather than silently returning incomplete evidence.
- User and meeting isolation are enforced through the owning analysis ID; no
  query may retrieve chunks from another analysis.

The future chatbot will consume this retrieval interface and add question
answering, conversation history, and citations in a separate design.

## Chunking and Scheduling

- Benchmark chunk sizes that produce approximately 16, 20, and 24 chunks for
  the worst-case transcription.
- Reject any variant whose effective Ollama prompt is truncated.
- Select the fastest passing chunk size on measured critical-fact retention.
- Process a relevance-ranked, chronologically distributed subset first.
- Persist every result immediately and reuse it during the complete pass.
- Benchmark chunk concurrency `1` and `2`; use `2` only if wall time improves
  without excessive swap, failures, or degraded throughput.
- Keep deterministic final consolidation as the safe baseline. Any model-based
  final consolidation must beat it on measured fact retention and remain
  within the time target.

## API Contract

Existing response fields remain unchanged. Add:

- `summary_stage`: `PRELIMINARY`, `PARTIAL`, or `COMPLETE`;
- `summary_is_final`: boolean;
- `summary_progress_percent`: completed summary chunks divided by total;
- `embedding_progress_percent`: completed embeddings divided by total;
- `summary_estimated_seconds_remaining`: ETA for summary generation only.

The existing `progress_percent` remains a backward-compatible alias for
`summary_progress_percent`. A summary at 100% can be final while embeddings
continue independently.

## Data Flow

1. Sanitize and clean 100% of the transcription.
2. Split it using the benchmark-selected chunk size.
3. Persist the analysis and all chunks.
4. Build and persist the deterministic preliminary summary.
5. Score chunks for explicit decisions, actions, dates, values, questions,
   negations, and evidence.
6. Schedule a chronologically distributed priority subset.
7. Persist each generated summary and rebuild the partial response.
8. Process every remaining chunk, reusing priority checkpoints.
9. Persist the complete final summary and mark `summary_is_final=true`.
10. Generate missing embeddings and update only embedding progress/status.
11. Once embeddings exist, expose bounded semantic retrieval for future RAG
    consumers without invoking a generative model.

## Failure and Restart Behavior

- Each successful summary and embedding is committed independently.
- Interrupted statuses resume automatically from missing work.
- Terminal failures do not retry on every service restart.
- A malformed or truncated model response gets one bounded retry/recovery.
- The preliminary and latest partial summary remain available after later
  summary or embedding failures.
- ETA is based only on work completed during the current attempt.

## Benchmark and Verification

Use `ia/tests/test_analisar.py` unchanged as the worst-case input. For every
candidate variant, capture:

- original and cleaned tokens;
- chunk count and effective prompt sizes;
- time to preliminary, partial, complete summary, and embeddings;
- total wall time;
- per-chunk generation time and retries;
- peak CPU and memory for IA, Ollama, and PostgreSQL;
- status, error, and required-field coverage;
- retention of the reference facts: CRM for 25 people, the 20/40 license
  discussion, plans on Monday, 27 machines, and the March/April cloud study.
- RAG retrieval isolation, stable ordering, bounded `top_k`, readiness errors,
  and evidence metadata.

The implementation is accepted only when the full automated suite passes and
an end-to-end run reaches `DONE`. If the current development machine misses the
12-minute target, report the measured result and retain the fastest
quality-passing configuration for a final benchmark on the production VPS.

## Out of Scope

- External inference APIs;
- GPU provisioning;
- chatbot generation, chat history, and conversational UI;
- dropping unprocessed portions of the final transcript;
- waiting for embeddings before showing a complete summary;
- changing or committing the user's manual worst-case transcription fixture.
